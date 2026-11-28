import unittest
from datetime import date
from decimal import Decimal as D

from app.cronograma import FASES, Actividad, Parametros, asignar_fases, calcular, predecesoras_constructivas
from app.cronograma.logica import fase_por_nombre
from app.cronograma.optimizador import Costos, Optimizador, Plazo, TOPE_CUADRILLA_AUTOMATICO, tope_automatico

LUNES = date(2026, 11, 30)


def act(i, nombre, hh, modulo=1):
    return Actividad(id=i, modulo=modulo, numero=i, nombre=nombre, horas_hombre=D(hh), personas=1)


OBRA = [
    act(1, "RETIRO DE CIELO RASO DE YESO", 64), act(2, "Muro de ladrillo de 6 huecos", 300), act(3, "Instalación eléctrica", 200),
    act(4, "Revoque grueso", 400), act(5, "Puerta de madera", 150), act(6, "Pintura látex", 400),
    act(7, "Instalación de artefactos sanitarios", 80), act(8, "Limpieza final", 30),
]


class TestEtapas(unittest.TestCase):
    def test_palabras_clave(self):
        esperado = {
            "RETIRO DE CIELO RASO DE YESO": 0,  # el retiro gana sobre «cielo raso»
            "Demolición de muro": 0, "Excavación manual": 1, "Hormigón armado en columnas": 1,
            "Instalación eléctrica": 2, "Instalación sanitaria": 2, "Piso de cerámica": 3, "Cielo falso": 3,
            "Puerta de madera": 4, "Pintura látex": 5, "Instalación de artefactos sanitarios": 6, "Limpieza final de obra": 7,
            "Instalación de faenas": 0,
        }
        for nombre, fase in esperado.items():
            self.assertEqual(fase_por_nombre(nombre), fase, nombre)

    def test_sin_palabra_clave_no_se_inventa(self):
        self.assertIsNone(fase_por_nombre("Ítem sin sentido"))
        self.assertIsNone(fase_por_nombre("Gastos varios"))  # «gas» no debe confundirse con «gastos»

    def test_acentos_y_mayusculas_no_importan(self):
        self.assertEqual(fase_por_nombre("HORMIGÓN ARMADO"), fase_por_nombre("hormigon armado"))

    def test_sin_palabra_clave_hereda_la_etapa_anterior(self):
        acts = [act(1, "Pintura látex", 10), act(2, "Trabajo raro", 10)]
        self.assertEqual(asignar_fases(acts), {1: 5, 2: 5})
        self.assertEqual(asignar_fases([act(1, "Trabajo raro", 10)]), {1: 1})  # el primero: obra gruesa

    def test_predecesoras_son_todos_los_de_la_etapa_anterior_con_items(self):
        acts = [act(1, "Retiro de piso", 8), act(2, "Demolición", 8), act(3, "Pintura", 8), act(4, "Pintura de rejas", 8)]
        pr = predecesoras_constructivas(acts)
        self.assertEqual(pr, {1: [], 2: [], 3: [1, 2], 4: [1, 2]})  # no hay etapas intermedias: salta a la anterior con ítems


class TestAcabadosFinales(unittest.TestCase):
    def _obra(self):
        def a(i, n, g=""):
            return Actividad(id=i, modulo=1, numero=i, nombre=n, horas_hombre=D(10), personas=1, grupo=g)
        return [a(1, "Retiro de piso"), a(2, "MESON H° A° C/REVESTIMIENTO CERAMICA ESMALTADA"), a(3, "Pintura látex"),
                a(4, "INSTALACION CAJONERIA BAJA PARA MESON"), a(5, "INSTALACION CAMPANA EXTRACTORA+ DUCTO"), a(6, "Limpieza final")]

    def test_cajoneria_depende_solo_del_meson_y_es_acabado_final(self):
        acts = self._obra()
        self.assertEqual(predecesoras_constructivas(acts)[4], [2])
        self.assertEqual(FASES[asignar_fases(acts)[4]], "Artefactos y accesorios")

    def test_campana_se_coloca_al_final_despues_de_la_pintura(self):
        acts = self._obra()
        self.assertEqual(predecesoras_constructivas(acts)[5], [3])
        self.assertEqual(FASES[asignar_fases(acts)[5]], "Artefactos y accesorios")

    def test_la_limpieza_espera_a_los_acabados(self):
        self.assertEqual(sorted(predecesoras_constructivas(self._obra())[6]), [4, 5])

    def test_cajoneria_sin_meson_cae_en_carpinteria(self):
        acts = [Actividad(1, 1, 1, "Instalación cajonería baja", D(10), 1), Actividad(2, 1, 2, "Pintura", D(10), 1)]
        self.assertEqual(FASES[asignar_fases(acts)[1]], "Carpintería")

    def test_el_nombre_del_modulo_ayuda_si_el_item_no_dice_nada(self):
        a = Actividad(1, 1, 1, "Trabajo raro", D(10), 1, grupo="INST. AGUA FRÍA")
        self.assertEqual(FASES[asignar_fases([a])[1]], "Instalaciones")


class TestMotorLogico(unittest.TestCase):
    def test_las_etapas_van_una_tras_otra(self):
        res = calcular(OBRA, [1], Parametros(LUNES, secuencia="logica_constructiva"))
        por_id = {c.actividad.id: c for c in res.actividades}
        for i in range(2, 9):
            self.assertGreater(por_id[i].inicio, por_id[i - 1].fin, i)
        self.assertEqual([c.actividad.id for c in res.actividades], list(range(1, 9)))  # en el orden del proyecto
        self.assertEqual([FASES[por_id[i].fase] for i in (1, 6, 8)],
                         ["Demolición y preliminares", "Pintura", "Limpieza y entrega"])

    def test_mismas_etapa_se_hacen_a_la_vez(self):
        acts = [act(1, "Retiro", 16), act(2, "Demolición", 16), act(3, "Pintura", 16)]
        res = calcular(acts, [1], Parametros(LUNES, secuencia="logica_constructiva"))
        por_id = {c.actividad.id: c for c in res.actividades}
        self.assertEqual(por_id[1].inicio, por_id[2].inicio)

    def test_editar_predecesoras_reemplaza_las_propuestas(self):
        res = calcular(OBRA, [1], Parametros(LUNES, secuencia="logica_constructiva"), None, {6: [4]})
        c6 = next(c for c in res.actividades if c.actividad.id == 6)
        self.assertTrue(c6.predecesora_manual)
        self.assertEqual(c6.predecesoras_definidas, [4])
        c5 = next(c for c in res.actividades if c.actividad.id == 5)
        self.assertFalse(c5.predecesora_manual)

    def test_se_ignoran_ids_desconocidos_y_autorreferencias(self):
        res = calcular(OBRA, [1], Parametros(LUNES, secuencia="logica_constructiva"), None, {6: [6, 999, 4]})
        self.assertEqual(next(c for c in res.actividades if c.actividad.id == 6).predecesoras_definidas, [4])

    def test_ciclo_se_nombra(self):
        with self.assertRaisesRegex(ValueError, r"ciclo.*2 → 3 → 2|ciclo.*3 → 2 → 3"):
            calcular(OBRA, [1], Parametros(LUNES, secuencia="logica_constructiva"), None, {2: [3], 3: [2]})

    def test_respeta_la_espera_del_pliego_de_la_predecesora(self):
        acts = [Actividad(1, 1, 1, "Hormigón", D(16), 2, espera_calendario=14), act(2, "Pintura", 16)]
        res = calcular(acts, [1], Parametros(LUNES, secuencia="logica_constructiva"))
        a, b = res.actividades
        self.assertGreaterEqual((b.inicio - a.fin).days, 14)


class TestOptimizadorAutomatico(unittest.TestCase):
    def _opt(self, plazo, tipo="calendario", tope=None, manuales=None):
        p = Parametros(LUNES, secuencia="logica_constructiva")
        tope = tope or tope_automatico(OBRA, D(8))
        return Optimizador(OBRA, [1], p, None, {a.id: 1 for a in OBRA}, tope, Plazo(plazo, tipo), Costos(), manuales)

    def test_tope_automatico_es_lo_que_hace_la_actividad_mayor_en_un_dia_con_techo_practico(self):
        self.assertEqual(tope_automatico(OBRA, D(8)), 40)  # 400 h-h ÷ 8 h = 50 personas para un día, pero el techo práctico es 40
        self.assertEqual(tope_automatico([act(1, "x", 16)], D(8)), 2)
        self.assertEqual(tope_automatico([act(1, "x", 100000)], D(8)), TOPE_CUADRILLA_AUTOMATICO)
        self.assertEqual(tope_automatico([], D(8)), 1)

    def test_calcula_las_personas_para_entrar_en_el_plazo(self):
        e = self._opt(40).cumplir_plazo()
        self.assertLessEqual(e.dias_calendario, 40)
        self.assertGreater(max(e.personas.values()), 1)

    def test_no_suma_gente_de_mas(self):
        e = self._opt(40).cumplir_plazo()
        for i in e.personas:  # quitarle una persona a cualquier actividad con más de una rompe el plazo
            if e.personas[i] > 1:
                menos = dict(e.personas)
                menos[i] -= 1
                self.assertGreater(self._opt(40)._escenario("x", menos).dias_calendario, 40, i)

    def test_plazo_mas_corto_pide_mas_personal(self):
        largo, corto = self._opt(60).cumplir_plazo(), self._opt(30).cumplir_plazo()
        self.assertGreaterEqual(corto.pico_personas, largo.pico_personas)

    def test_plazo_imposible_queda_en_el_minimo_con_el_tope(self):
        o = self._opt(2)
        e = o.cumplir_plazo()
        self.assertGreater(e.dias_calendario, 2)
        self.assertEqual(e.dias_habiles, o._minimo_con_tope().dias_habiles)

    def test_las_predecesoras_editadas_cambian_el_resultado(self):
        sin = self._opt(40).cumplir_plazo()
        con = self._opt(40, manuales={i: [] for i in range(2, 9)}).cumplir_plazo()  # todo a la vez
        self.assertLessEqual(con.dias_calendario, 40)
        self.assertNotEqual(sin.personas, con.personas)


if __name__ == "__main__":
    unittest.main()
