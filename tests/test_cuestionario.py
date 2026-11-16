"""
Tests de app/cuestionario.py: preguntas, etiquetas y validación de los
envíos nuevos (P-04).
"""

import pytest

from app import cuestionario
from app.cuestionario import PREGUNTAS, validar


class TestPreguntas:

    def test_etiquetas_legibles(self):
        assert PREGUNTAS['horas_solo'].etiqueta('8+') == 'Más de 8 horas'
        assert PREGUNTAS['vivienda_tipo'].etiqueta('finca') == 'Finca/Campo'
        assert PREGUNTAS['tiene_jardin'].etiqueta('si') == 'Sí'

    def test_etiqueta_desconocida_o_texto_libre(self):
        assert PREGUNTAS['horas_solo'].etiqueta('9-12') is None
        assert PREGUNTAS['referencias'].etiqueta('algo') is None

    def test_obligatorias(self):
        opcionales = {campo for campo, p in PREGUNTAS.items() if not p.obligatoria}
        assert opcionales == {'mascotas_detalles', 'referencias'}


class TestValidar:

    def test_envio_valido(self, respuestas_validas):
        limpio, errores = validar(respuestas_validas)

        assert errores == {}
        assert limpio['vivienda_tipo'] == 'casa'
        assert limpio['tiene_jardin'] is True
        assert limpio['tiene_mascotas'] is False
        assert limpio['horas_solo'] == '0-4'

    def test_no_contestado_es_none(self, respuestas_validas):
        limpio, _ = validar(respuestas_validas)

        assert limpio['mascotas_detalles'] is None
        assert limpio['referencias'] is None

    def test_limpio_tiene_todas_las_preguntas_y_ninguna_mas(self, respuestas_validas):
        limpio, _ = validar({**respuestas_validas, 'csrf_token': 'x', 'otra': 'y'})

        assert set(limpio) == set(PREGUNTAS)

    def test_envio_vacio(self):
        limpio, errores = validar({})

        obligatorias = {campo for campo, p in PREGUNTAS.items() if p.obligatoria}
        assert set(errores) == obligatorias
        assert set(errores.values()) == {cuestionario.MENSAJE_OBLIGATORIO}
        # Nada se convierte en False por no contestarse
        assert all(valor is None for valor in limpio.values())

    @pytest.mark.parametrize('campo, valor', [
        ('vivienda_tipo', 'Casa'),
        ('vivienda_propia', 'Sí'),
        ('tiene_jardin', 'quizá'),
        ('horas_solo', '4-6 horas'),
        ('emergencia_veterinaria', 'rezar'),
        ('compromiso_gastos', 'tal vez'),
    ])
    def test_opcion_fuera_de_la_lista(self, respuestas_validas, campo, valor):
        _, errores = validar({**respuestas_validas, campo: valor})

        assert errores == {campo: cuestionario.MENSAJE_OPCION}

    def test_no_se_compromete_es_false(self, respuestas_validas):
        limpio, errores = validar({**respuestas_validas, 'compromiso_gastos': 'no'})

        assert errores == {}
        assert limpio['compromiso_gastos'] is False

    def test_espacios_cuentan_como_vacio(self, respuestas_validas):
        _, errores = validar({**respuestas_validas, 'motivo_adopcion': '   '})

        assert errores == {'motivo_adopcion': cuestionario.MENSAJE_OBLIGATORIO}

    def test_textos_sin_espacios_sobrantes(self, respuestas_validas):
        limpio, _ = validar({**respuestas_validas, 'referencias': '  Ana  ', 'horas_solo': ' 8+ '})

        assert limpio['referencias'] == 'Ana'
        assert limpio['horas_solo'] == '8+'

    def test_texto_demasiado_largo(self, respuestas_validas):
        largo = 'x' * (cuestionario.LONGITUD_MAXIMA + 1)
        _, errores = validar({**respuestas_validas, 'referencias': largo})

        assert errores == {'referencias': cuestionario.MENSAJE_LARGO}

    @pytest.mark.parametrize('campo, valor, mensaje', [
        ('tiene_jardin', True, cuestionario.MENSAJE_OPCION),
        ('horas_solo', 8, cuestionario.MENSAJE_OPCION),
        ('experiencia_previa', True, cuestionario.MENSAJE_TEXTO),
        ('referencias', {'a': 1}, cuestionario.MENSAJE_TEXTO),
        ('motivo_adopcion', ['x'], cuestionario.MENSAJE_TEXTO),
    ])
    def test_tipos_no_validos(self, respuestas_validas, campo, valor, mensaje):
        _, errores = validar({**respuestas_validas, campo: valor})

        assert errores == {campo: mensaje}

    @pytest.mark.parametrize('campo', ['experiencia_previa', 'referencias'])
    def test_texto_con_nul_no_es_valido(self, respuestas_validas, campo):
        """PostgreSQL no admite \\u0000 en JSONB: daría un 500 al guardar."""
        _, errores = validar({**respuestas_validas, campo: 'hola\x00mundo'})

        assert errores == {campo: cuestionario.MENSAJE_TEXTO}

    def test_valor_null_cuenta_como_no_contestado(self, respuestas_validas):
        _, errores = validar({**respuestas_validas, 'referencias': None, 'horas_solo': None})

        assert errores == {'horas_solo': cuestionario.MENSAJE_OBLIGATORIO}


class TestDependencias:

    def test_tiene_mascotas_exige_detalles(self, respuestas_validas):
        _, errores = validar({**respuestas_validas, 'tiene_mascotas': 'si'})

        assert errores == {'mascotas_detalles': cuestionario.MENSAJE_DETALLES}

    def test_tiene_mascotas_con_detalles(self, respuestas_validas):
        limpio, errores = validar({**respuestas_validas, 'tiene_mascotas': 'si',
                                   'mascotas_detalles': 'Un gato de 3 años'})

        assert errores == {}
        assert limpio['tiene_mascotas'] is True
        assert limpio['mascotas_detalles'] == 'Un gato de 3 años'

    def test_detalles_con_error_propio_no_se_pisa(self, respuestas_validas):
        largo = 'x' * (cuestionario.LONGITUD_MAXIMA + 1)
        _, errores = validar({**respuestas_validas, 'tiene_mascotas': 'si', 'mascotas_detalles': largo})

        assert errores == {'mascotas_detalles': cuestionario.MENSAJE_LARGO}

    def test_sin_mascotas_no_exige_detalles(self, respuestas_validas):
        _, errores = validar(respuestas_validas)

        assert errores == {}


def test_claves_desconocidas(respuestas_validas):
    assert cuestionario.claves_desconocidas(respuestas_validas) == []
    assert cuestionario.claves_desconocidas({**respuestas_validas, 'z': 1, 'a': 2}) == ['a', 'z']
