import unittest
from datetime import date
from decimal import Decimal

from app.cronograma import Actividad, Parametros, calcular, repartir_en_frentes
from app.cronograma.optimizador import Costos, Optimizador, Plazo, dias_calendario, dias_del_plazo, pico_de_personas

LUNES = date(2026, 12, 7)
D = Decimal


def act(id_, modulo, numero, hh, personas=1, **kw):
    return Actividad(id=id_, modulo=modulo, numero=numero, nombre=f"A{numero}", horas_hombre=D(hh), personas=personas, **kw)


def opt(acts, plazo=Plazo(), costos=Costos(), tope=30, sab=False, secuencia="todo_en_serie"):
    p = Parametros(LUNES, trabaja_sabados=sab, secuencia=secuencia)
    return Optimizador(acts, [1], p, None, {a.id: a.personas for a in acts}, tope, plazo, costos)


class TestPlazoCalendarioVsHabiles(unittest.TestCase):
    def test_dias_calendario_cuentan_fines_de_semana(self):
        # 10 días hábiles desde un lunes: termina el viernes de la 2ª semana = día calendario 12
        res = calcular([act(1, 1, 1, "80", 1)], [1], Parametros(LUNES))
        self.assertEqual(res.dias_habiles, 10)
        self.assertEqual(dias_calendario(res, LUNES), 12)
        self.assertEqual(dias_del_plazo(res, LUNES, "habiles"), 10)
        self.assertEqual(dias_del_plazo(res, LUNES, "calendario"), 12)

    def test_sabado_trabajado_acorta_los_dias_calendario(self):
        res = calcular([act(1, 1, 1, "80", 1)], [1], Parametros(LUNES, trabaja_sabados=True))
        self.assertEqual(res.dias_habiles, 10)
        self.assertEqual(dias_calendario(res, LUNES), 11)  # lun-sáb, domingo (cuenta), lun-jue


class TestCumplirPlazo(unittest.TestCase):
    def test_suma_personas_solo_hasta_entrar_en_el_plazo(self):
        a = [act(1, 1, 1, "80", 1)]  # 10 días con 1 persona
        e = opt(a, Plazo(5, "habiles")).cumplir_plazo()
        self.assertEqual(e.personas[1], 2)  # 80/(2×8) = 5 días: justo el plazo
        self.assertEqual(e.dias_habiles, 5)
        self.assertEqual(e.personas_agregadas, 1)

    def test_plazo_en_dias_calendario(self):
        a = [act(1, 1, 1, "80", 1)]
        e = opt(a, Plazo(7, "calendario")).cumplir_plazo()  # 5 días hábiles = lun..vie = 5 corridos
        self.assertLessEqual(e.dias_calendario, 7)
        self.assertEqual(e.personas[1], 2)
        e = opt(a, Plazo(5, "calendario")).cumplir_plazo()
        self.assertEqual(e.dias_calendario, 5)

    def test_solo_acelera_la_ruta_critica(self):
        # dos actividades en paralelo: la corta tiene holgura y no debe recibir gente
        a = [act(1, 1, 1, "160", 1), act(2, 1, 2, "16", 1)]
        e = opt(a, Plazo(10, "habiles"), secuencia="todo_en_paralelo").cumplir_plazo()
        self.assertEqual(e.personas[2], 1)
        self.assertEqual(e.personas[1], 2)

    def test_plazo_imposible_devuelve_el_minimo_con_el_tope(self):
        a = [act(1, 1, 1, "800", 1)]  # con tope 4: 800/(4×8) = 25 días
        e = opt(a, Plazo(5, "habiles"), tope=4).cumplir_plazo()
        self.assertEqual(e.personas[1], 4)
        self.assertEqual(e.dias_habiles, 25)

    def test_sin_plazo_es_un_error(self):
        with self.assertRaises(ValueError):
            opt([act(1, 1, 1, "80")]).cumplir_plazo()

    def test_tipo_de_plazo_invalido(self):
        with self.assertRaises(ValueError):
            opt([act(1, 1, 1, "80")], Plazo(5, "otro"))


class TestMasRapido(unittest.TestCase):
    def test_llega_al_minimo_que_permite_el_tope(self):
        a = [act(1, 1, 1, "80", 1), act(2, 1, 2, "80", 1)]
        e = opt(a, tope=10).mas_rapido()
        self.assertEqual(e.dias_habiles, 2)  # 80/(10×8) = 1 día cada una, en serie
        self.assertTrue(all(n == 10 for n in e.personas.values()))

    def test_paralelo_con_dos_caminos_criticos_iguales(self):
        a = [act(1, 1, 1, "80", 1), act(2, 1, 2, "80", 1)]
        e = opt(a, tope=10, secuencia="todo_en_paralelo").mas_rapido()
        self.assertEqual(e.dias_habiles, 1)

    def test_no_pasa_del_tope(self):
        e = opt([act(1, 1, 1, "800", 1)], tope=3).mas_rapido()
        self.assertEqual(e.personas[1], 3)

    def test_respeta_la_duracion_minima_del_pliego(self):
        e = opt([act(1, 1, 1, "80", 1, duracion_minima=4)], tope=30).mas_rapido()
        self.assertEqual(e.dias_habiles, 4)
        self.assertLessEqual(e.personas[1], 3)  # más gente no acorta nada: no se suma gente inútil


class TestMenorCosto(unittest.TestCase):
    def test_sin_costo_indirecto_no_acelera(self):
        e = opt([act(1, 1, 1, "80", 1)], costos=Costos(D(0), D(100))).menor_costo()
        self.assertEqual(e.personas_agregadas, 0)

    def test_acelera_mientras_el_ahorro_supere_el_costo(self):
        # 1 día calendario ahorrado vale 1000 Bs; cada persona extra cuesta 500
        a = [act(1, 1, 1, "80", 1)]
        e = opt(a, costos=Costos(D(1000), D(500))).menor_costo()
        base = opt(a, costos=Costos(D(1000), D(500))).manual()
        self.assertLess(e.costo_total, base.costo_total)
        self.assertGreater(e.personas[1], 1)

    def test_si_la_gente_sale_mas_cara_no_suma(self):
        a = [act(1, 1, 1, "80", 1)]
        e = opt(a, costos=Costos(D(10), D(100000))).menor_costo()
        self.assertEqual(e.personas[1], 1)


class TestPico(unittest.TestCase):
    def test_pico_suma_actividades_que_se_solapan(self):
        res = calcular([act(1, 1, 1, "80", 3), act(2, 1, 2, "80", 2)], [1], Parametros(LUNES, secuencia="todo_en_paralelo"))
        self.assertEqual(pico_de_personas(res), 5)
        res = calcular([act(1, 1, 1, "80", 3), act(2, 1, 2, "80", 2)], [1], Parametros(LUNES, secuencia="todo_en_serie"))
        self.assertEqual(pico_de_personas(res), 3)


class TestPredecesoras(unittest.TestCase):
    def test_en_serie_cada_una_depende_de_la_anterior(self):
        res = calcular([act(1, 1, 1, "16", 1), act(2, 1, 2, "16", 1), act(3, 1, 3, "16", 1)], [1],
                       Parametros(LUNES, secuencia="todo_en_serie"))
        pred = {c.actividad.id: c.predecesoras for c in res.actividades}
        self.assertEqual(pred, {1: [], 2: [1], 3: [2]})

    def test_modulos_en_serie_dependen_de_la_que_cierra_el_modulo_anterior(self):
        a = [act(1, 1, 1, "16", 1), act(2, 1, 2, "64", 1), act(3, 2, 1, "16", 1)]
        res = calcular(a, [1, 2], Parametros(LUNES, secuencia="modulos_en_serie"))
        pred = {c.actividad.id: c.predecesoras for c in res.actividades}
        self.assertEqual(pred[1], [])
        self.assertEqual(pred[2], [])
        self.assertEqual(pred[3], [2])  # la actividad más larga del módulo 1 es la que empuja

    def test_en_paralelo_no_hay_predecesoras(self):
        res = calcular([act(1, 1, 1, "16", 1), act(2, 1, 2, "16", 1)], [1], Parametros(LUNES, secuencia="todo_en_paralelo"))
        self.assertTrue(all(c.predecesoras == [] for c in res.actividades))


def opt_frentes(acts, plazo, tope=30, sab=False, secuencia="todo_en_serie", costos=Costos()):
    return opt(acts, plazo, costos, tope, sab, secuencia)


class TestFrentes(unittest.TestCase):
    def test_reparto_equilibrado_y_estable(self):
        acts = [act(i, 1, i, h) for i, h in enumerate([100, 90, 80, 70, 10, 10, 10, 10], 1)]
        f = repartir_en_frentes(acts, 2)
        carga = {1: 0, 2: 0}
        for a in acts:
            carga[f[a.id]] += int(a.horas_hombre)
        self.assertLess(abs(carga[1] - carga[2]), 40)
        self.assertEqual(f, repartir_en_frentes(acts, 2))  # determinista
        self.assertEqual(set(f.values()), {1, 2})

    def test_nunca_mas_frentes_que_actividades(self):
        acts = [act(1, 1, 1, "8"), act(2, 1, 2, "8")]
        self.assertEqual(set(repartir_en_frentes(acts, 10).values()), {1, 2})

    def test_cada_frente_hace_sus_actividades_una_tras_otra_y_los_frentes_en_paralelo(self):
        acts = [act(i, 1, i, "16") for i in range(1, 5)]  # 2 días cada una con 1 persona
        res = calcular(acts, [1], Parametros(LUNES, secuencia="frentes_de_trabajo", frentes=2))
        self.assertEqual(res.dias_habiles, 4)  # 2 frentes × 2 actividades × 2 días
        self.assertEqual(sorted({c.frente for c in res.actividades}), [1, 2])
        for f in (1, 2):
            cs = sorted((c for c in res.actividades if c.frente == f), key=lambda c: c.inicio)
            self.assertEqual(len(cs), 2)
            self.assertGreater(cs[1].inicio, cs[0].fin)
            self.assertEqual(cs[1].predecesoras, [cs[0].actividad.id])

    def test_un_frente_equivale_a_todo_en_serie(self):
        acts = [act(i, 1, i, "16") for i in range(1, 5)]
        a = calcular(acts, [1], Parametros(LUNES, secuencia="frentes_de_trabajo", frentes=1))
        b = calcular(acts, [1], Parametros(LUNES, secuencia="todo_en_serie"))
        self.assertEqual(a.dias_habiles, b.dias_habiles)

    def test_abre_frentes_cuando_la_secuencia_no_alcanza(self):
        # 8 actividades de 1 día mínimo en serie: nunca menos de 8 días hábiles, aunque se ponga toda la gente
        acts = [act(i, 1, i, "40") for i in range(1, 9)]
        o = opt_frentes(acts, Plazo(4, "habiles"))
        self.assertGreater(o.cumplir_plazo().dias_habiles, 4)  # solo sumar gente no alcanza
        e = o.abrir_frentes()
        self.assertIsNotNone(e)
        self.assertLessEqual(e.dias_habiles, 4)
        self.assertGreaterEqual(e.frentes, 2)
        self.assertEqual(e.secuencia, "frentes_de_trabajo")

    def test_elige_el_menor_numero_de_frentes(self):
        acts = [act(i, 1, i, "40") for i in range(1, 9)]
        alt = opt_frentes(acts, Plazo(4, "habiles")).alternativas_frentes()
        self.assertEqual(alt[0].frentes, min(e.frentes for e in alt))
        self.assertEqual([e.frentes for e in alt], sorted(e.frentes for e in alt))

    def test_personal_total_es_la_suma_de_cuadrillas_de_los_frentes(self):
        acts = [act(i, 1, i, "80") for i in range(1, 7)]
        e = opt_frentes(acts, Plazo(10, "habiles")).abrir_frentes()
        por_frente = {}
        for c in e.resultado.actividades:
            por_frente[c.frente] = max(por_frente.get(c.frente, 0), c.actividad.personas)
        self.assertEqual(e.personal_total, sum(por_frente.values()))
        self.assertGreaterEqual(e.personal_total, e.pico_personas)

    def test_cota_minima_de_personal(self):
        # nadie puede cumplir con menos que horas-hombre ÷ (días hábiles × jornada)
        acts = [act(i, 1, i, "160") for i in range(1, 7)]  # 960 h-h
        e = opt_frentes(acts, Plazo(10, "habiles")).abrir_frentes()
        self.assertGreaterEqual(e.personal_total, 960 / (10 * 8))
        self.assertLessEqual(e.personal_total, 2 * 960 / (10 * 8))  # y no se pasa del doble en este caso

    def test_plazo_imposible_por_el_tope_de_personas_devuelve_none(self):
        acts = [act(1, 1, 1, "800"), act(2, 1, 2, "8")]  # la primera, con 4 personas, nunca baja de 25 días
        self.assertIsNone(opt_frentes(acts, Plazo(5, "habiles"), tope=4).abrir_frentes())

    def test_una_espera_entre_actividades_de_un_mismo_frente_se_evita_separandolas(self):
        # 21 días de fraguado entre A1 y A2: en serie no entra en 5 días; en dos frentes sí
        acts = [act(1, 1, 1, "8", espera_calendario=21), act(2, 1, 2, "8")]
        self.assertGreater(opt_frentes(acts, Plazo(5, "habiles")).cumplir_plazo().dias_habiles, 5)
        self.assertEqual(opt_frentes(acts, Plazo(5, "habiles")).abrir_frentes().frentes, 2)

    def test_respeta_el_maximo_de_frentes(self):
        acts = [act(i, 1, i, "40") for i in range(1, 9)]
        self.assertIsNone(opt_frentes(acts, Plazo(2, "habiles")).abrir_frentes(max_frentes=2))
        self.assertIsNotNone(opt_frentes(acts, Plazo(2, "habiles")).abrir_frentes(max_frentes=8))

    def test_el_plan_cumple_en_dias_calendario(self):
        acts = [act(i, 1, i, "40") for i in range(1, 9)]
        e = opt_frentes(acts, Plazo(8, "calendario")).abrir_frentes()
        self.assertLessEqual(e.dias_calendario, 8)


if __name__ == "__main__":
    unittest.main()
