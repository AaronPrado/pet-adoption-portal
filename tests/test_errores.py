"""
Tests del manejo de errores.
"""

import io


def test_archivo_demasiado_grande_redirige_con_aviso(client, auth_headers_admin):
    """Una subida de más de 5 MB vuelve al formulario en lugar de dar un 500."""
    grande = io.BytesIO(b'0' * (5 * 1024 * 1024 + 1))
    response = client.post('/mascotas/admin/nueva', data={
        'nombre': 'Rocky',
        'foto': (grande, 'foto.png'),
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/mascotas/admin/nueva')

    with client.session_transaction() as sesion:
        mensajes = [m for _, m in sesion.get('_flashes', [])]
    assert 'El archivo es demasiado grande. Máximo 5MB.' in mensajes
