"""Pruebas de bibliotecas y vinculación de APU con SQLite en memoria.

Necesitan:  pip install -r requirements.txt   (si falta SQLAlchemy o Pydantic, se saltan).
"""
import importlib.util
import unittest

from app.costos import obtener_predefinido
from decimal import Decimal

HAY_DEPS = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "pydantic"))

if HAY_DEPS:
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import models
    from app.db.base import Base
    from app.importers.b1_parser import ItemB1, ModuloB1, ResultadoB1
    from app.importers.biblioteca_excel import crear_plantilla_bytes, leer_biblioteca_excel
    from app.importers.spec_parser import EspecItem, RecursoRequerido, ResultadoEspecificaciones
    from app.services import apu as apu_srv
    from app.services import costos as costos_srv
    from app.services import bibliotecas as bib_srv
    from app.services import proyectos as srv


def _b1():
    def item(n, desc, cant_txt):
        return ItemB1(numero=n, descripcion=desc, descripcion_original=desc, unidad="m²", unidad_normalizada="m2",
                      cantidad=Decimal(cant_txt.replace(",", ".")), cantidad_texto=cant_txt, orden=n, pagina=1,
                      modulo_codigo="M01")
    items = [item(1, "RETIRO DE CIELO RASO DE YESO", "32,34"),
             item(2, "CONTRAPISO DE HORMIGON E=5 CM + EMPEDRADO", "0,60"),
             item(3, "MESON H° A° C/REVESTIMIENTO CERAMICA ESMALTADA", "8,95")]
    return ResultadoB1(modulos=[ModuloB1("M01", "PRELIMINARES", 1, items)], alertas=[], estrategia="demo")


def _esp(**por_numero):
    """_esp(n1=[(tipo, nombre), ...]) -> especificaciones con esos recursos para cada número."""
    items = []
    for clave, recursos in por_numero.items():
        n = int(clave[1:])
        items.append(EspecItem(numero=n, titulo=f"ITEM {n}", unidad_spec="m2", modulo_spec=None, pagina_inicio=n,
                               recursos=[RecursoRequerido(t, nombre, None, None, None, n, nombre) for t, nombre in recursos]))
    return ResultadoEspecificaciones(items=items)


@unittest.skipUnless(HAY_DEPS, "Faltan dependencias (sqlalchemy/pydantic).")
class TestBibliotecasYVinculacion(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.bib = bib_srv.crear_desde_excel(self.db, "Mi biblioteca", leer_biblioteca_excel(crear_plantilla_bytes()))
        self.apu1, self.apu2 = self.bib.apus
        self.p = srv.crear_desde_b1(self.db, _b1(), "Demo", None)
        self.p.modelo_costos = obtener_predefinido("costo_directo").a_dict()  # estas pruebas miden el APU, sin indirectos
        self.items = {it.numero: it for m in self.p.modulos for it in m.items}

    def tearDown(self):
        self.db.close()

    def _con_pliego(self, **kw):
        srv.guardar_especificaciones(self.db, self.p, _esp(**kw), "esp.pdf")

    def _salida(self, n):
        out = srv.a_proyecto_out(self.p)
        return [i for m in out.modulos for i in m.items if i.numero == n][0]

    def _contar(self, modelo, *condiciones):
        return self.db.scalar(select(func.count()).select_from(modelo).where(*condiciones))

    # ---- biblioteca ----
    def test_importar_biblioteca(self):
        self.assertEqual((len(self.bib.apus), len(self.bib.recursos)), (2, 9))  # catálogo sin duplicados
        out = bib_srv.a_biblioteca_out(self.bib)
        self.assertEqual((out.total_apus, out.total_lineas), (2, 9))
        self.assertEqual([a.costo for a in bib_srv.listar_apus(self.db, self.bib)], ["16.80", "75.80"])
        self.assertEqual(self.apu2.unidad_normalizada, "m2")

    # ---- candidatos ----
    def test_candidatos(self):
        c = apu_srv.candidatos_para_item(self.db, self.items[1])
        self.assertEqual((c[0].apu_id, c[0].confianza), (self.apu1.id, "alta"))
        self.assertEqual(apu_srv.candidatos_para_item(self.db, self.items[3]), [])

    # ---- modos de recursos ----
    def test_hibrido_copia_el_apu_y_calcula_el_precio(self):
        self._con_pliego(n1=[("mano_obra", "Peón")])
        apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "hibrido")
        it = self._salida(1)
        self.assertEqual((it.apu.estado, it.apu.costo, it.precio_unitario, it.total), ("completo", "16.80", "16.80", "543.31"))
        peon = [l for l in it.apu.lineas if l.descripcion == "Peón"][0]
        self.assertEqual((peon.origen_dato, peon.requerido_por_pliego), ("ambos", True))
        # es una COPIA: editarla no toca la biblioteca
        copia = self.db.get(models.Apu, it.apu.id)
        self.assertEqual((copia.proyecto_id, copia.biblioteca_id, copia.origen_apu_id), (self.p.id, None, self.apu1.id))
        self.assertEqual(len(self.apu1.lineas), 2)

    def test_apu_incompleto_no_pone_precio(self):
        self._con_pliego(n2=[("material", "Cemento portland"), ("equipo", "Hormigonera")])
        apu_srv.vincular_item(self.db, self.items[2], self.apu2.id, "hibrido")
        it = self._salida(2)
        self.assertEqual((it.apu.estado, it.apu.pendientes, it.apu.costo, it.precio_unitario), ("incompleto", 1, None, None))
        hormigonera = [l for l in it.apu.lineas if l.descripcion == "Hormigonera"][0]
        self.assertEqual((hormigonera.origen_dato, hormigonera.estado, hormigonera.cantidad), ("pliego", "pendiente", None))
        self.assertEqual(len(it.apu.lineas), 8)  # 7 de la biblioteca + la hormigonera pendiente

    def test_modo_pliego_y_modo_biblioteca(self):
        self._con_pliego(n1=[("mano_obra", "Peón"), ("equipo", "Hormigonera")])
        apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "pliego")
        self.assertEqual(sorted(l.descripcion for l in self._salida(1).apu.lineas), ["Hormigonera", "Peón"])
        avisos = apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "biblioteca")
        self.assertEqual(len(self._salida(1).apu.lineas), 2)  # las del APU del usuario; se reemplazó la copia anterior
        self.assertEqual(self._contar(models.Apu, models.Apu.proyecto_id == self.p.id), 1)
        self.assertTrue(any("Hormigonera" in a for a in avisos))
        self.assertIn("apu_aviso", [a.codigo for a in self.p.alertas if a.origen == "apu"])

    def test_sin_apu_se_usa_solo_el_pliego(self):
        self._con_pliego(n3=[("material", "Cerámica esmaltada"), ("mano_obra", "Albañil")])
        apu_srv.vincular_item(self.db, self.items[3], None, "hibrido")
        it = self._salida(3)
        self.assertEqual((len(it.apu.lineas), it.apu.estado, it.precio_unitario), (2, "incompleto", None))
        self.assertIsNone(it.apu.origen_apu_id)

    # ---- modelo de costos del proyecto ----
    def test_el_precio_del_item_sale_del_modelo_y_cambia_con_el_modelo(self):
        self._con_pliego(n1=[("mano_obra", "Peón")])
        apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "hibrido")
        self.assertEqual(self._salida(1).precio_unitario, "16.80")  # costo directo
        problemas = costos_srv.asignar_modelo(self.db, self.p, obtener_predefinido("bolivia_b2").a_dict())
        self.assertEqual(problemas, [])
        it = self._salida(1)
        self.assertGreater(float(it.precio_unitario), 16.80)
        self.assertEqual((it.apu.costo, it.apu.precio), ("16.80", it.precio_unitario))
        self.assertEqual(it.apu.desglose[-1].codigo, "it")
        self.assertEqual(self.p.modelo_costos["codigo"], "bolivia_b2")

    def test_modelo_invalido_no_se_guarda(self):
        malo = obtener_predefinido("bolivia_b2").a_dict()
        malo["secciones"][1]["pasos"][0]["base"] = ["no_existe"]
        antes = dict(self.p.modelo_costos)
        self.assertTrue(costos_srv.asignar_modelo(self.db, self.p, malo))
        self.assertEqual(self.p.modelo_costos, antes)
        self.assertTrue(costos_srv.asignar_modelo(self.db, self.p, {"basura": 1}))

    def test_errores_no_dejan_cambios(self):
        with self.assertRaises(LookupError):
            apu_srv.vincular_item(self.db, self.items[1], 9999, "hibrido")
        with self.assertRaises(ValueError):
            apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "otro")
        self.assertIsNone(self.items[1].apu_id)

    # ---- equivalencias y vinculación automática ----
    def test_la_equivalencia_confirmada_se_recuerda(self):
        self.assertEqual(self._contar(models.Equivalencia), 0)
        apu_srv.vincular_item(self.db, self.items[1], self.apu1.id, "hibrido", recordar=True)
        self.assertEqual(self._contar(models.Equivalencia), 1)
        c = apu_srv.candidatos_para_item(self.db, self.items[1])[0]
        self.assertEqual((c.apu_id, c.motivo, c.confianza), (self.apu1.id, "equivalencia", "alta"))

    def test_vinculacion_automatica_solo_aplica_lo_seguro(self):
        r = apu_srv.vincular_automatico(self.db, self.p, "hibrido")
        self.assertEqual(r, {"vinculados": 2, "solo_pliego": 0, "por_revisar": 0, "sin_candidato": 1})
        it = self.items[1]
        self.assertEqual((it.vinculo_confianza, it.vinculo_confirmado, it.modo_precio), ("alta", False, "apu"))
        self.assertEqual(self._contar(models.Equivalencia), 0)  # lo automático no se "aprende"
        self.assertIsNone(self.items[3].apu_id)
        # volver a correrlo no pisa lo ya vinculado
        self.assertEqual(apu_srv.vincular_automatico(self.db, self.p, "hibrido")["vinculados"], 0)

    def test_vinculacion_automatica_en_modo_pliego_cubre_lo_que_la_biblioteca_no_tiene(self):
        self._con_pliego(n3=[("material", "Cerámica esmaltada")])
        r = apu_srv.vincular_automatico(self.db, self.p, "pliego")
        self.assertEqual((r["vinculados"], r["solo_pliego"]), (2, 1))
        self.assertIsNotNone(self.items[3].apu_id)

    def test_confianza_minima_invalida(self):
        with self.assertRaises(ValueError):
            apu_srv.vincular_automatico(self.db, self.p, "hibrido", minimo_confianza="nunca")

    # ---- edición de líneas del APU ----
    def _apu_pliego(self, n, *recursos):
        self._con_pliego(**{f"n{n}": list(recursos)})
        apu_srv.vincular_item(self.db, self.items[n], None, "pliego")
        return self._salida(n).apu.lineas

    def test_cargar_cantidades_y_precios_completa_el_apu_y_da_precio(self):
        ceramica, albanil = self._apu_pliego(3, ("material", "Cerámica esmaltada"), ("mano_obra", "Albañil"))
        self.assertIsNone(self._salida(3).precio_unitario)
        apu_srv.editar_linea(self.db, ceramica.id, {"cantidad": "1,05", "precio_unitario": "45"})
        self.assertIsNone(self._salida(3).precio_unitario)  # falta la mano de obra
        apu_srv.editar_linea(self.db, albanil.id, {"cantidad": "0,8", "precio_unitario": "30"})
        it = self._salida(3)
        self.assertEqual((it.apu.estado, it.apu.costo, it.precio_unitario), ("completo", "71.25", "71.25"))  # 47,25 + 24
        self.assertEqual([l.origen_rendimiento for l in it.apu.lineas], ["manual", "manual"])
        self.assertEqual(it.total, "637.69")  # 8,95 × 71,25

    def test_el_origen_se_puede_elegir_y_vaciar_la_cantidad_lo_deja_pendiente(self):
        (linea,) = self._apu_pliego(3, ("mano_obra", "Albañil"))
        apu_srv.editar_linea(self.db, linea.id, {"cantidad": "0,5", "origen_rendimiento": "medido"})
        self.assertEqual(self._salida(3).apu.lineas[0].origen_rendimiento, "medido")
        apu_srv.editar_linea(self.db, linea.id, {"origen_rendimiento": "referencial"})
        self.assertEqual(self._salida(3).apu.lineas[0].origen_rendimiento, "referencial")
        apu_srv.editar_linea(self.db, linea.id, {"cantidad": ""})
        l = self._salida(3).apu.lineas[0]
        self.assertEqual((l.cantidad, l.origen_rendimiento, l.estado), (None, "pendiente", "pendiente"))

    def test_el_precio_de_un_recurso_se_aplica_a_todos_los_apu_del_proyecto(self):
        (alb2,) = self._apu_pliego(2, ("mano_obra", "Albañil"))
        self._apu_pliego(3, ("mano_obra", "albañil"))
        apu_srv.editar_linea(self.db, alb2.id, {"precio_unitario": "30"})
        precios = [self._salida(n).apu.lineas[0].precio_unitario for n in (2, 3)]
        self.assertEqual(precios, ["30", "30"])
        (recurso,) = srv.a_proyecto_out(self.p).recursos
        self.assertEqual((recurso.nombre, recurso.usos, recurso.precio, recurso.estado), ("Albañil", 2, "30", "completo"))
        # sin aplicar a todos, solo cambia esa línea
        apu_srv.editar_linea(self.db, alb2.id, {"precio_unitario": "35"}, aplicar_precio_a_recurso=False)
        self.assertEqual(srv.a_proyecto_out(self.p).recursos[0].estado, "varios")

    def test_fijar_el_precio_de_un_recurso_desde_la_lista_del_proyecto(self):
        self._apu_pliego(2, ("mano_obra", "Albañil"), ("material", "Yeso"))
        self._apu_pliego(3, ("mano_obra", "Albañil"))
        clave = apu_srv.clave_recurso("mano_obra", "Albañil")
        apu_srv.fijar_precio_recurso(self.db, self.p, clave, "30,5")
        recursos = {r.nombre: r for r in srv.a_proyecto_out(self.p).recursos}
        self.assertEqual((recursos["Albañil"].precio, recursos["Albañil"].usos), ("30.5", 2))
        self.assertEqual((recursos["Yeso"].estado, recursos["Yeso"].precio), ("sin_precio", None))
        with self.assertRaises(LookupError):
            apu_srv.fijar_precio_recurso(self.db, self.p, "equipo|no existe", "1")

    def test_agregar_un_recurso_propio_crea_el_apu_y_reutiliza_precios(self):
        (alb,) = self._apu_pliego(3, ("mano_obra", "Albañil"))
        apu_srv.editar_linea(self.db, alb.id, {"precio_unitario": "30"})
        self.assertIsNone(self.items[1].apu_id)
        apu_srv.agregar_linea(self.db, self.items[1], "material", "Yeso", "kg", "8,5", "1,2")
        apu_srv.agregar_linea(self.db, self.items[1], "mano_obra", "Albañil", "h", "0,4")  # el precio ya existe: 30
        it = self._salida(1)
        self.assertEqual([(l.descripcion, l.origen_dato, l.origen_rendimiento) for l in it.apu.lineas],
                         [("Yeso", "manual", "manual"), ("Albañil", "manual", "manual")])
        self.assertEqual((it.apu.lineas[1].precio_unitario, it.precio_unitario, it.modo_precio), ("30", "22.20", "apu"))  # 10,20 + 12

    def test_eliminar_una_linea_recalcula(self):
        yeso, alb = self._apu_pliego(3, ("material", "Yeso"), ("mano_obra", "Albañil"))
        apu_srv.editar_linea(self.db, yeso.id, {"cantidad": "2", "precio_unitario": "5"})
        self.assertIsNone(self._salida(3).precio_unitario)  # el albañil sigue pendiente
        apu_srv.eliminar_linea(self.db, alb.id)
        it = self._salida(3)
        self.assertEqual((len(it.apu.lineas), it.precio_unitario), (1, "10.00"))

    def test_errores_al_editar(self):
        (linea,) = self._apu_pliego(3, ("mano_obra", "Albañil"))
        for malo in ({"cantidad": "abc"}, {"precio_unitario": "-3"}, {"origen_rendimiento": "inventado"}):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                apu_srv.editar_linea(self.db, linea.id, malo)
        with self.assertRaises(LookupError):
            apu_srv.editar_linea(self.db, 99999, {"cantidad": "1"})
        with self.assertRaises(ValueError):  # las líneas de la biblioteca no se editan desde el proyecto
            apu_srv.editar_linea(self.db, self.apu1.lineas[0].id, {"cantidad": "1"})
        with self.assertRaises(ValueError):
            apu_srv.agregar_linea(self.db, self.items[1], "otro", "X")
        with self.assertRaises(ValueError):
            apu_srv.agregar_linea(self.db, self.items[1], "material", "  ")
        self.assertEqual(self._salida(3).apu.lineas[0].cantidad, None)  # nada quedó a medias

    # ---- borrado ----
    def test_borrar_el_proyecto_borra_sus_copias_pero_no_la_biblioteca(self):
        apu_srv.vincular_automatico(self.db, self.p, "hibrido")
        self.assertEqual(self._contar(models.Apu, models.Apu.proyecto_id.is_not(None)), 2)
        self.db.delete(self.p)
        self.db.commit()
        self.assertEqual(self._contar(models.Apu, models.Apu.proyecto_id.is_not(None)), 0)
        self.assertEqual(self._contar(models.Apu, models.Apu.biblioteca_id.is_not(None)), 2)


if __name__ == "__main__":
    unittest.main()
