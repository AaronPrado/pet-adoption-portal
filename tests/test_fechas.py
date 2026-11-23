"""
Fechas en la zona horaria del refugio (B4.5, P-26): filtro `fecha_local`.

Las fechas se guardan en UTC sin zona (`utcnow()`); el filtro las trata como
UTC y las pasa a `ZONA_HORARIA` antes de formatearlas.
"""

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from flask import render_template_string

from app import create_app
from app.fechas import fecha_local
from config import config


def utc(*args):
    """Fecha como la guarda la base de datos: UTC sin zona."""
    return datetime(*args, tzinfo=UTC).replace(tzinfo=None)


@pytest.fixture
def zona_madrid(app):
    return app.config['ZONA_HORARIA']


class TestFechaLocal:

    def test_la_zona_por_defecto_es_madrid(self, app):
        assert app.config['ZONA_HORARIA'] == 'Europe/Madrid'

    def test_en_invierno_suma_una_hora(self, zona_madrid):
        # 15 de noviembre: CET (UTC+1)
        assert fecha_local(utc(2026, 11, 15, 13, 53), zona_madrid, con_hora=True) \
            == '15 de noviembre de 2026, 14:53'

    def test_en_verano_suma_dos_horas(self, zona_madrid):
        # 15 de julio: CEST (UTC+2)
        assert fecha_local(utc(2026, 7, 15, 13, 53), zona_madrid, con_hora=True) \
            == '15 de julio de 2026, 15:53'

    def test_cerca_de_medianoche_cambia_el_dia(self, zona_madrid):
        assert fecha_local(utc(2026, 11, 15, 23, 30), zona_madrid) == '16 de noviembre de 2026'
        assert fecha_local(utc(2026, 7, 15, 22, 30), zona_madrid) == '16 de julio de 2026'

    def test_cambio_de_hora_de_marzo(self, zona_madrid):
        # El 29/03/2026 a la 01:00 UTC las 02:00 CET saltan a las 03:00 CEST
        assert fecha_local(utc(2026, 3, 29, 0, 59), zona_madrid, con_hora=True) \
            == '29 de marzo de 2026, 01:59'
        assert fecha_local(utc(2026, 3, 29, 1, 0), zona_madrid, con_hora=True) \
            == '29 de marzo de 2026, 03:00'

    def test_cambio_de_hora_de_octubre(self, zona_madrid):
        # El 25/10/2026 a la 01:00 UTC las 03:00 CEST vuelven a las 02:00 CET
        assert fecha_local(utc(2026, 10, 25, 0, 59), zona_madrid, con_hora=True) \
            == '25 de octubre de 2026, 02:59'
        assert fecha_local(utc(2026, 10, 25, 1, 0), zona_madrid, con_hora=True) \
            == '25 de octubre de 2026, 02:00'

    def test_una_fecha_con_zona_se_convierte(self, zona_madrid):
        valor = datetime(2026, 11, 15, 14, 0, tzinfo=timezone(timedelta(hours=-5)))

        assert fecha_local(valor, zona_madrid, con_hora=True) == '15 de noviembre de 2026, 20:00'

    def test_otra_zona(self):
        assert fecha_local(utc(2026, 11, 15, 13, 0), 'Atlantic/Canary', con_hora=True) \
            == '15 de noviembre de 2026, 13:00'

    @pytest.mark.parametrize('mes, nombre', list(enumerate(
        ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
         'octubre', 'noviembre', 'diciembre'], start=1)))
    def test_meses_en_espanol_sin_depender_del_locale(self, zona_madrid, mes, nombre):
        assert fecha_local(utc(2026, mes, 10, 12, 0), zona_madrid) == f'10 de {nombre} de 2026'

    @pytest.mark.parametrize('valor', ['15/11/2026', 42, '<b>x</b>'])
    def test_un_valor_que_no_es_fecha_se_devuelve_tal_cual(self, zona_madrid, valor):
        assert fecha_local(valor, zona_madrid, con_hora=True) == valor

    def test_el_filtro_escapa_un_texto(self, app):
        with app.test_request_context():
            assert render_template_string('{{ f|fecha_local }}', f='<b>x</b>') == '&lt;b&gt;x&lt;/b&gt;'

    def test_sin_valor_devuelve_vacio(self, zona_madrid):
        assert fecha_local(None, zona_madrid) == ''


class TestFiltroEnPlantillas:

    def test_filtro_registrado_con_la_zona_de_la_configuracion(self, app):
        with app.test_request_context():
            html = render_template_string("{{ f|fecha_local }}|{{ f|fecha_local(hora=true) }}",
                                          f=utc(2026, 7, 15, 22, 30))

        assert html == '16 de julio de 2026|16 de julio de 2026, 00:30'

    def test_zona_configurable(self):
        class Canarias(config['testing']):
            ZONA_HORARIA = 'Atlantic/Canary'

        config['canarias'] = Canarias
        try:
            app = create_app('canarias')
        finally:
            del config['canarias']

        with app.test_request_context():
            html = render_template_string("{{ f|fecha_local(hora=true) }}", f=utc(2026, 7, 15, 22, 30))

        assert html == '15 de julio de 2026, 23:30'

    def test_zona_desconocida_falla_al_arrancar(self):
        class Rota(config['testing']):
            ZONA_HORARIA = 'Mundo/Inventado'

        config['rota'] = Rota
        try:
            with pytest.raises(RuntimeError, match='ZONA_HORARIA no válida'):
                create_app('rota')
        finally:
            del config['rota']


def test_tzdata_con_version_fija_en_requirements():
    """Docker slim y Windows no traen la base de zonas: zoneinfo la toma de tzdata."""
    from pathlib import Path
    texto = (Path(__file__).resolve().parent.parent / 'requirements.txt').read_text(encoding='utf-8')

    assert re.search(r'^tzdata==\d{4}\.\d+$', texto, re.M)
