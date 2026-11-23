"""
Tests de app/cuestionario.py: preguntas, etiquetas y validación de los
envíos nuevos (P-04).
"""

import re

import pytest

from app import cuestionario
from app.cuestionario import PREGUNTAS, respuesta_legible, validar


class TestPreguntas:

    def test_etiquetas_legibles(self):
        assert PREGUNTAS['horas_solo'].etiqueta('8+') == 'Más de 8 horas'
        assert PREGUNTAS['vivienda_tipo'].etiqueta('finca') == 'Finca o campo'
        assert PREGUNTAS['tiene_jardin'].etiqueta('si') == 'Sí'

    def test_etiqueta_desconocida_o_texto_libre(self):
        assert PREGUNTAS['horas_solo'].etiqueta('9-12') is None
        assert PREGUNTAS['referencias'].etiqueta('algo') is None

    def test_obligatorias(self):
        opcionales = {campo for campo, p in PREGUNTAS.items() if not p.obligatoria}
        assert opcionales == {'mascotas_detalles', 'referencias'}


class TestFormatoGuardado:
    """
    Los `value` y las claves se guardan en `cuestionario_json`: cambiarlos
    dejaría sin etiqueta las solicitudes ya enviadas y rompería la API. Si de
    verdad hay que cambiarlos, hace falta una migración de datos.
    """

    def test_claves_de_las_preguntas(self):
        assert list(PREGUNTAS) == [
            'vivienda_tipo', 'vivienda_propia', 'tiene_jardin', 'tiene_mascotas', 'mascotas_detalles',
            'experiencia_previa', 'horas_solo', 'emergencia_veterinaria', 'motivo_adopcion',
            'compromiso_gastos', 'compromiso_tiempo', 'referencias']

    def test_values_de_las_opciones(self):
        values = {campo: tuple(valor for valor, _ in p.opciones) for campo, p in PREGUNTAS.items() if p.opciones}

        assert values == {
            'vivienda_tipo': ('casa', 'apartamento', 'finca'),
            'vivienda_propia': ('propia', 'alquilada'),
            'tiene_jardin': ('si', 'no'),
            'tiene_mascotas': ('si', 'no'),
            'horas_solo': ('0-4', '4-8', '8+'),
            'emergencia_veterinaria': ('veterinario', 'consulta', 'espera'),
            'compromiso_gastos': ('si', 'no'),
            'compromiso_tiempo': ('si', 'no'),
        }

    def test_si_no_se_guardan_como_booleano(self):
        si_no = {campo for campo, p in PREGUNTAS.items() if p.si_no}

        assert si_no == {'tiene_jardin', 'tiene_mascotas', 'compromiso_gastos', 'compromiso_tiempo'}


class TestTextos:
    """P-27: tuteo en todo el cuestionario y rangos de horas sin solapes."""

    def textos(self):
        for pregunta in PREGUNTAS.values():
            yield pregunta.texto
            if pregunta.ayuda:
                yield pregunta.ayuda
            for _, etiqueta in pregunta.opciones or ():
                yield etiqueta

    def test_rangos_de_horas_sin_solapes(self):
        assert PREGUNTAS['horas_solo'].opciones == (
            ('0-4', 'Menos de 4 horas'), ('4-8', 'De 4 a 8 horas'), ('8+', 'Más de 8 horas'))

    def test_tuteo(self):
        usted = re.compile(r'\b(usted|[Tt]iene|[Ee]s vivienda|[Ss]e compromete|[Pp]uede|estaría|actuaría)\b')

        assert [texto for texto in self.textos() if usted.search(texto)] == []

    def test_cada_enunciado_es_una_pregunta(self):
        """El resumen de errores antepone el enunciado al mensaje («¿…? Esta pregunta es obligatoria.»)."""
        for pregunta in PREGUNTAS.values():
            assert pregunta.texto.startswith('¿') and pregunta.texto.endswith('?'), pregunta.texto

    def test_compromisos_dicen_a_que_se_compromete(self):
        """P-12: «No puedo garantizarlo» no se entiende sin su pregunta, que ahora es el legend."""
        assert PREGUNTAS['compromiso_gastos'].etiqueta('si') == 'Sí, me comprometo'
        assert PREGUNTAS['compromiso_tiempo'].etiqueta('no') == 'No puedo garantizarlo'
        assert 'gastos veterinarios' in PREGUNTAS['compromiso_gastos'].texto


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



class TestResumenDeErrores:
    """Textos del resumen de errores del formulario: la pregunta y su error, en el orden del formulario."""

    def test_orden_del_formulario_y_enunciado(self):
        errores = {'mascotas_detalles': cuestionario.MENSAJE_DETALLES, 'vivienda_tipo': cuestionario.MENSAJE_OPCION}

        resumen = cuestionario.resumen_de_errores(errores)

        assert list(resumen.items()) == [
            ('vivienda_tipo', f'{PREGUNTAS["vivienda_tipo"].texto} {cuestionario.MENSAJE_OPCION}'),
            ('mascotas_detalles', f'{PREGUNTAS["mascotas_detalles"].texto} {cuestionario.MENSAJE_DETALLES}'),
        ]

    def test_sin_errores(self):
        assert cuestionario.resumen_de_errores({}) == {}

    def test_ignora_claves_que_no_son_preguntas(self):
        assert cuestionario.resumen_de_errores({'otra': 'x'}) == {}

def test_claves_desconocidas(respuestas_validas):
    assert cuestionario.claves_desconocidas(respuestas_validas) == []
    assert cuestionario.claves_desconocidas({**respuestas_validas, 'z': 1, 'a': 2}) == ['a', 'z']


class TestRespuestaLegible:
    """P-10: las respuestas guardadas se muestran con su etiqueta, no con el `value`."""

    @pytest.mark.parametrize('campo, valor, esperado', [
        ('horas_solo', '8+', 'Más de 8 horas'),
        ('emergencia_veterinaria', 'espera', 'Esperaría a ver cómo evoluciona'),
        ('vivienda_tipo', 'finca', 'Finca o campo'),
        ('tiene_jardin', True, 'Sí'),
        ('tiene_mascotas', False, 'No'),
        ('compromiso_gastos', True, 'Sí, me comprometo'),
        ('compromiso_tiempo', False, 'No puedo garantizarlo'),
        ('motivo_adopcion', 'Quiero un perro', 'Quiero un perro'),
    ])
    def test_etiquetas(self, campo, valor, esperado):
        assert respuesta_legible({campo: valor}, campo) == esperado

    @pytest.mark.parametrize('respuestas', [{}, {'referencias': None}, {'referencias': '  '}, None, 'texto'])
    def test_sin_respuesta(self, respuestas):
        assert respuesta_legible(respuestas, 'referencias') == cuestionario.SIN_RESPUESTA == 'Sin respuesta'

    @pytest.mark.parametrize('campo, valor, esperado', [
        # Cuestionarios antiguos (seed y fixtures, B2.6): se muestran tal cual
        ('horas_solo', '4-6 horas', '4-6 horas'),
        ('tiene_jardin', 'Sí', 'Sí'),
        ('tiene_jardin', 'si', 'Sí'),
        ('horas_solo', True, 'Sí'),
        ('horas_solo', ['8+'], "['8+']"),
        ('vivienda_tipo', 3, '3'),
        ('experiencia', 'Si, Beagle antes', 'Si, Beagle antes'),
        ('experiencia', False, 'No'),
    ])
    def test_datos_antiguos_no_dan_error(self, campo, valor, esperado):
        assert respuesta_legible({campo: valor}, campo) == esperado

    def test_secciones_cubren_todas_las_preguntas_en_orden(self):
        campos = [campo for _, preguntas in cuestionario.SECCIONES for campo, _ in preguntas]

        assert campos == list(PREGUNTAS)
        assert [titulo for titulo, _ in cuestionario.SECCIONES] == [
            'Vivienda', 'Experiencia', 'Motivación y compromisos']

    def test_toda_pregunta_tiene_seccion(self):
        with pytest.raises(TypeError):
            cuestionario.Pregunta('Sin sección')

    def test_es_filtro_de_jinja(self, app):
        plantilla = app.jinja_env.from_string("{{ r|respuesta_legible('horas_solo') }}")

        assert plantilla.render(r={'horas_solo': '8+'}) == 'Más de 8 horas'
