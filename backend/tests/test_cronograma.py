import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS

from app.cronograma import Actividad, Parametros, actividades_del_proyecto, calcular
from app.cronograma.motor import Calendario, duracion_dias, personas_necesarias

LUNES = date(2026, 12, 7)  # es lunes
D = Decimal


def act(id_, modulo, numero, hh, personas=2, **kw):
    return Actividad(id=id_, modulo=modulo, numero=numero, nombre=f"Actividad {numero}", horas_hombre=D(hh),
                     personas=personas, **kw)


def por_id(res):
    return {c.actividad.id: c for c in res.actividades}


class TestDuracion(unittest.TestCase):
    def test_duracion_por_horas_hombre(self):
        self.assertEqual(duracion_dias(act(1, 1, 1, "80", 2), D(8)), 5)    # 80 / (2×8)
        self.assertEqual(duracion_dias(act(1, 1, 1, "80.1", 2), D(8)), 6)  # redondea hacia arriba
        self.assertEqual(duracion_dias(act(1, 1, 1, "1", 5), D(8)), 1)     # mínimo 1 día
        self.assertEqual(duracion_dias(act(1, 1, 1, "8", 5, duracion_minima=2), D(8)), 2)

    def test_personas_necesarias_para_un_plazo(self):
        self.assertEqual(personas_necesarias(D("80"), 5, D(8)), 2)
        self.assertEqual(personas_necesarias(D("81"), 5, D(8)), 3)
        with self.assertRaises(ValueError):
            personas_necesarias(D("80"), 0, D(8))


class TestCalendario(unittest.TestCase):
    def test_salta_fines_de_semana_y_feriados(self):
        cal = Calendario(Parametros(LUNES, feriados=frozenset({date(2026, 12, 9)})))
        self.assertEqual([cal.fecha(i) for i in range(5)],
                         [date(2026, 12, 7), date(2026, 12, 8), date(2026, 12, 10), date(2026, 12, 11), date(2026, 12, 14)])

    def test_si_empieza_en_fin_de_semana_arranca_el_lunes(self):
        self.assertEqual(Calendario(Parametros(date(2026, 12, 5))).fecha(0), LUNES)  # sábado

    def test_con_sabados(self):
        cal = Calendario(Parametros(LUNES, trabaja_sabados=True))
        self.assertEqual(cal.fecha(5), date(2026, 12, 12))  # sábado
        self.assertEqual(cal.fecha(6), date(2026, 12, 14))

    def test_espera_en_dias_corridos_a_habiles(self):
        self.assertEqual(Calendario(Parametros(LUNES)).laborables(21), 15)
        self.assertEqual(Calendario(Parametros(LUNES, trabaja_sabados=True)).laborables(21), 18)
        self.assertEqual(Calendario(Parametros(LUNES)).laborables(0), 0)


class TestCalculo(unittest.TestCase):
    def test_una_actividad(self):
        r = calcular([act(1, 1, 1, "80")], [1], Parametros(LUNES))
        c = r.actividades[0]
        self.assertEqual((c.duracion, c.inicio, c.fin, c.critica, c.holgura), (5, LUNES, date(2026, 12, 11), True, 0))
        self.assertEqual((r.fecha_fin, r.dias_habiles), (date(2026, 12, 11), 5))

    def test_modulos_en_serie_con_actividades_en_paralelo_dentro_del_modulo(self):
        acts = [act(1, 1, 1, "80"), act(2, 1, 2, "48"), act(3, 2, 3, "32")]  # 5 d y 3 d | 2 d
        r = calcular(acts, [1, 2], Parametros(LUNES))
        c = por_id(r)
        self.assertEqual(c[1].inicio, c[2].inicio)          # paralelas dentro del módulo
        self.assertEqual(c[3].inicio, date(2026, 12, 14))   # tras la más larga del módulo anterior
        self.assertEqual((c[1].critica, c[2].critica, c[3].critica), (True, False, True))
        self.assertEqual(c[2].holgura, 2)
        self.assertEqual((r.fecha_fin, r.dias_habiles), (date(2026, 12, 15), 7))

    def test_la_espera_obligatoria_retrasa_al_siguiente_modulo(self):
        acts = [act(1, 1, 1, "80", espera_calendario=21), act(2, 2, 2, "16")]
        c = por_id(calcular(acts, [1, 2], Parametros(LUNES)))
        self.assertGreaterEqual((c[2].inicio - c[1].fin).days, 21)   # al menos 21 días corridos después
        self.assertEqual(c[2].inicio, Calendario(Parametros(LUNES)).fecha(5 + 15))

    def test_feriado_alarga_la_actividad(self):
        r = calcular([act(1, 1, 1, "80")], [1], Parametros(LUNES, feriados=frozenset({date(2026, 12, 9)})))
        self.assertEqual(r.actividades[0].fin, date(2026, 12, 14))

    def test_sabados(self):
        a = [act(1, 1, 1, "112")]  # 7 días de trabajo
        self.assertEqual(calcular(a, [1], Parametros(LUNES)).actividades[0].fin, date(2026, 12, 15))
        self.assertEqual(calcular(a, [1], Parametros(LUNES, trabaja_sabados=True)).actividades[0].fin, date(2026, 12, 14))

    def test_todo_en_serie_y_todo_en_paralelo(self):
        acts = [act(1, 1, 1, "32"), act(2, 1, 2, "32"), act(3, 2, 3, "32")]  # 2 días cada una
        serie = por_id(calcular(acts, [1, 2], Parametros(LUNES, secuencia="todo_en_serie")))
        self.assertEqual([serie[i].inicio for i in (1, 2, 3)], [LUNES, date(2026, 12, 9), date(2026, 12, 11)])
        par = calcular(acts, [1, 2], Parametros(LUNES, secuencia="todo_en_paralelo"))
        self.assertEqual({c.inicio for c in par.actividades}, {LUNES})
        self.assertEqual(par.dias_habiles, 2)

    def test_mas_personas_acortan(self):
        base = calcular([act(1, 1, 1, "80", personas=2)], [1], Parametros(LUNES)).dias_habiles
        mas = calcular([act(1, 1, 1, "80", personas=5)], [1], Parametros(LUNES)).dias_habiles
        self.assertEqual((base, mas), (5, 2))

    def test_un_modulo_sin_actividades_no_corta_la_cadena(self):
        c = por_id(calcular([act(1, 1, 1, "32"), act(3, 3, 3, "32")], [1, 2, 3], Parametros(LUNES)))
        self.assertEqual(c[3].inicio, date(2026, 12, 9))

    def test_hitos_y_atraso(self):
        acts = [act(1, 1, 1, "80"), act(2, 2, 2, "32")]  # módulo 1 termina el 11/12; módulo 2, el 15/12
        r = calcular(acts, [1, 2], Parametros(LUNES), hitos={1: date(2026, 12, 11), 2: date(2026, 12, 11)})
        m = {x.id: x for x in r.modulos}
        self.assertEqual(m[1].atraso_dias, 0)   # termina justo el día del hito
        self.assertEqual(m[2].atraso_dias, 2)   # 14 y 15 de diciembre: 2 días hábiles después del hito
        r2 = calcular(acts, [1, 2], Parametros(LUNES), hitos={2: date(2026, 12, 30)})
        self.assertEqual(r2.modulos[1].atraso_dias, 0)
        self.assertEqual((r2.modulos[0].hito, r2.modulos[1].hito), (None, date(2026, 12, 30)))

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            calcular([act(1, 1, 1, "8")], [1], Parametros(LUNES, secuencia="otra"))
        with self.assertRaises(ValueError):
            calcular([act(1, 1, 1, "8")], [1], Parametros(LUNES, horas_jornada=D(0)))

    def test_sin_actividades(self):
        r = calcular([], [1], Parametros(LUNES))
        self.assertEqual((r.actividades, r.fecha_fin, r.dias_habiles), ([], None, 0))


def item(id_, numero, cantidad, lineas, datos=()):
    apu = None if lineas is None else NS(lineas=[NS(tipo=t, cantidad=c, unidad=u) for t, c, u in lineas])
    return NS(id=id_, numero=numero, descripcion=f"Ítem {numero}", cantidad=cantidad, apu=apu,
              datos_tecnicos=[NS(tipo=t, valor=v) for t, v in datos])


class TestPuente(unittest.TestCase):
    def proyecto(self, *items):
        return NS(modulos=[NS(id=1, items=list(items))])

    def test_horas_hombre_desde_el_apu(self):
        p = self.proyecto(item(1, 1, D("10"), [("material", D("2"), "kg"), ("mano_obra", D("0.8"), "h"), ("mano_obra", D("0.4"), "h")]))
        acts, sin = actividades_del_proyecto(p, 2, {}, D(8))
        self.assertEqual(sin, [])
        self.assertEqual((acts[0].horas_hombre, acts[0].personas), (D("12.0"), 2))   # 10 × (0,8 + 0,4)

    def test_los_dias_se_convierten_con_la_jornada(self):
        p = self.proyecto(item(1, 1, D("5"), [("mano_obra", D("0.5"), "jornal"), ("mano_obra", D("0.5"), "día")]))
        acts, _ = actividades_del_proyecto(p, 2, {}, D(8))
        # «jornal» no es una unidad conocida: se toma como horas y se avisa; «día» se multiplica por 8
        self.assertEqual(acts[0].horas_hombre, D("5") * (D("0.5") + D("0.5") * 8))
        self.assertIn("jornal", acts[0].nota)

    def test_personas_por_item(self):
        p = self.proyecto(item(1, 1, D("1"), [("mano_obra", D("8"), "h")]), item(2, 2, D("1"), [("mano_obra", D("8"), "h")]))
        acts, _ = actividades_del_proyecto(p, 2, {2: 4}, D(8))
        self.assertEqual([a.personas for a in acts], [2, 4])

    def test_no_se_programa_lo_que_no_tiene_datos(self):
        p = self.proyecto(
            item(1, 1, D("1"), None),
            item(2, 2, D("1"), [("material", D("1"), "kg")]),
            item(3, 3, D("1"), [("mano_obra", None, "h")]),
            item(4, 4, D("0"), [("mano_obra", D("1"), "h")]),
            item(5, 5, None, [("mano_obra", D("1"), "h")]),
            item(6, 6, D("1"), [("mano_obra", D("0"), "h")]),
            item(7, 7, D("1"), [("mano_obra", D("1"), "h")]),
        )
        acts, sin = actividades_del_proyecto(p, 2, {}, D(8))
        self.assertEqual([a.numero for a in acts], [7])
        motivos = {i.numero: m for i, m in sin}
        self.assertEqual(sorted(motivos), [1, 2, 3, 4, 5, 6])
        self.assertIn("No tiene APU", motivos[1])
        self.assertIn("no tiene mano de obra", motivos[2])
        self.assertIn("Faltan cantidades", motivos[3])

    def test_esperas_del_pliego(self):
        p = self.proyecto(item(1, 1, D("1"), [("mano_obra", D("8"), "h")],
                               datos=[("espera", "21 dias"), ("espera", "48 horas"), ("espera", "12 horas"), ("dosificacion", "1:2:3")]))
        (a,), _ = actividades_del_proyecto(p, 2, {}, D(8))
        self.assertEqual((a.espera_calendario, a.duracion_minima), (21, 2))
        self.assertIn("21 días", a.nota)
        p2 = self.proyecto(item(1, 1, D("1"), [("mano_obra", D("8"), "h")], datos=[("espera", "3 a 4 horas")]))
        (b,), _ = actividades_del_proyecto(p2, 2, {}, D(8))
        self.assertEqual((b.espera_calendario, b.duracion_minima), (0, 1))  # menos de 24 horas no cambia nada


if __name__ == "__main__":
    unittest.main()
