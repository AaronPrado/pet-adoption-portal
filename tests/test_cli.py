"""
Tests de los comandos CLI.
"""

from app.models import Usuario


def test_crear_admin(runner):
    result = runner.invoke(args=['crear-admin', '--email', 'Jefa@Refugio.com', '--nombre', 'Jefa',
                                 '--password', 'clave-segura-1'])

    assert result.exit_code == 0, result.output
    admin = Usuario.query.filter_by(email='jefa@refugio.com').one()
    assert admin.is_admin()
    assert admin.check_password('clave-segura-1')


def test_crear_admin_asciende_usuario_existente(runner, usuario_adoptante):
    result = runner.invoke(args=['crear-admin', '--email', 'adoptante@test.com', '--nombre', 'Pepe',
                                 '--password', 'clave-segura-2'])

    assert result.exit_code == 0, result.output
    assert Usuario.query.filter_by(email='adoptante@test.com').one().is_admin()


def test_crear_admin_rechaza_contrasena_corta(runner):
    result = runner.invoke(args=['crear-admin', '--email', 'a@b.com', '--nombre', 'A',
                                 '--password', 'corta'])

    assert result.exit_code != 0
    assert Usuario.query.count() == 0
