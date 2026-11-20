"""
Tests de lo necesario para desplegar: health check y proxy inverso.
"""

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app, db
from app.models import Usuario
from config import TestingConfig


class TestHealth:

    def test_ok(self, client):
        response = client.get('/health')

        assert response.status_code == 200
        assert response.get_json() == {'status': 'ok'}

    def test_base_de_datos_caida(self, client, monkeypatch):
        def fallar(*args, **kwargs):
            raise OperationalError('SELECT 1', {}, Exception('conexión rechazada'))
        monkeypatch.setattr(db.session, 'execute', fallar)

        response = client.get('/health')

        assert response.status_code == 503
        assert response.get_json() == {'status': 'error', 'database': 'unreachable'}


class TestProxyInverso:

    @pytest.fixture
    def cliente(self, monkeypatch):
        """App con límite de intentos activo y el número de proxies indicado."""
        def crear(proxies):
            monkeypatch.setattr(TestingConfig, 'RATELIMIT_ENABLED', True)
            monkeypatch.setattr(TestingConfig, 'TRUSTED_PROXIES', proxies)
            app = create_app('testing')
            ctx = app.app_context()
            ctx.push()
            db.create_all()
            db.session.add(Usuario(email='a@test.com', nombre='A', password='password123'))
            db.session.commit()
            return app.test_client(), ctx
        yield crear

    def intentos_fallidos(self, client, ip, n):
        return [
            client.post('/auth/login', data={'email': 'a@test.com', 'password': 'mala'},
                        headers={'X-Forwarded-For': ip}).status_code
            for _ in range(n)
        ]

    def test_con_proxy_limita_por_ip_real(self, cliente):
        client, ctx = cliente(1)
        try:
            assert self.intentos_fallidos(client, '203.0.113.1', 6)[-1] == 429
            # Otra IP real detrás del mismo proxy no está bloqueada
            assert self.intentos_fallidos(client, '203.0.113.2', 1) == [400]
        finally:
            db.drop_all()
            ctx.pop()

    def test_sin_proxy_ignora_x_forwarded_for(self, cliente):
        client, ctx = cliente(0)
        try:
            self.intentos_fallidos(client, '203.0.113.1', 5)
            # Cambiar la cabecera no sirve para saltarse el límite
            assert self.intentos_fallidos(client, '203.0.113.2', 1) == [429]
        finally:
            db.drop_all()
            ctx.pop()
