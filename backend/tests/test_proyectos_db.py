"""Pruebas de guardado y cálculo con una base SQLite en memoria.

Necesitan:  pip install -r requirements.txt   (si falta SQLAlchemy o Pydantic, se saltan).
"""
import importlib.util
import os
import unittest
from decimal import Decimal
from pathlib import Path

HAY_DEPS = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "pydantic"))
PDF_REAL = Path(os.environ.get("B1_PDF", "/mnt/user-data/uploads/items_san_pedro_.pdf"))
ESP_REAL = Path(os.environ.get("ESP_PDF", "/mnt/user-data/uploads/ESP_TECNICAS_MANT_C_C_SAN_PEDRO_D-7_12_DE_OCTUBRE.pdf"))

if HAY_DEPS:
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import models
    from app.db.base import Base
    from app.importers.b1_parser import AlertaB1, ItemB1, ModuloB1, ResultadoB1, parse_b1
    from app.importers.spec_parser import (
        DatoTecnico, EspecItem, RecursoRequerido, ResultadoEspecificaciones, parse_especificaciones,
    )
    from app.services import proyectos as srv


def _resultado_demo() -> "ResultadoB1":
    def item(n, desc, unidad, cant_txt, orden, modulo):
        return ItemB1(numero=n, descripcion=desc, descripcion_original=desc, unidad=unidad,
                      unidad_normalizada=unidad.replace("²", "2"), cantidad=Decimal(cant_txt.replace(",", ".")),
                      cantidad_texto=cant_txt, orden=orden, pagina=1, modulo_codigo=modulo)
    m1 = ModuloB1("M01", "PRELIMINARES", 1, [item(1, "RETIRO DE CIELO", "m²", "32,34", 1, "M01"),
                                             item(2, "RETIRO DE PISO", "m²", "7,30", 2, "M01")])
    m2 = ModuloB1("M02", "OBRA GRUESA", 2, [item(3, "MESON", "m²", "8,95", 3, "M02")])
    return ResultadoB1(modulos=[m1, m2], alertas=[AlertaB1("info", "demo", "alerta de prueba", 2)], estrategia="demo")


@unittest.skipUnless(HAY_DEPS, "Faltan dependencias (sqlalchemy/pydantic).")
class TestProyectosDB(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()

    def tearDown(self):
        self.db.close()

    def test_guarda_estructura_y_alertas(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", "demo.pdf")
        out = srv.a_proyecto_out(p)
        self.assertEqual((len(out.modulos), out.total_items, out.items_con_precio), (2, 3, 0))
        self.assertEqual(out.total, "0.00")
        self.assertEqual(out.alertas[0].item_numero, 2)
        self.assertTrue(all(it.bloqueado for m in out.modulos for it in m.items))

    def test_precio_y_totales(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        item1 = p.modulos[0].items[0]
        srv.actualizar_precio(self.db, item1.id, "10,50")
        out = srv.a_proyecto_out(self.db.get(models.Proyecto, p.id))
        it = out.modulos[0].items[0]
        self.assertEqual((it.precio_unitario, it.total, it.modo_precio), ("10.50", "339.57", "directo"))  # 32,34 × 10,50
        self.assertEqual(out.modulos[0].total, "339.57")
        self.assertEqual((out.total, out.items_con_precio), ("339.57", 1))

    def test_precio_invalido_y_quitar_precio(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        iid = p.modulos[0].items[0].id
        for malo in ["abc", "-5"]:
            with self.assertRaises(ValueError):
                srv.actualizar_precio(self.db, iid, malo)
        srv.actualizar_precio(self.db, iid, "5")
        srv.actualizar_precio(self.db, iid, "")
        item = self.db.get(models.Item, iid)
        self.assertEqual((item.precio_unitario, item.modo_precio), (None, "pendiente"))
        with self.assertRaises(LookupError):
            srv.actualizar_precio(self.db, 9999, "1")

    def test_borrar_proyecto_borra_todo(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        self.db.delete(p)
        self.db.commit()
        for modelo in (models.Proyecto, models.Modulo, models.Item, models.AlertaImportacion):
            self.assertEqual(self.db.scalar(select(func.count()).select_from(modelo)), 0, modelo.__name__)

    @unittest.skipUnless(PDF_REAL.exists(), "No se encontró el PDF real.")
    def test_guarda_el_b1_real(self):
        p = srv.crear_desde_b1(self.db, parse_b1(PDF_REAL), "San Pedro", PDF_REAL.name)
        out = srv.a_proyecto_out(p)
        self.assertEqual((len(out.modulos), out.total_items), (7, 24))
        self.assertEqual(srv.listar_resumenes(self.db)[0].total_items, 24)

    def _esp_demo(self):
        return ResultadoEspecificaciones(items=[
            EspecItem(numero=1, titulo="RETIRO DE CIELO", unidad_spec="m2", modulo_spec="MOD-1 X", pagina_inicio=1,
                      recursos=[RecursoRequerido("mano_obra", "Peón", None, None, None, 1, "- Peón")],
                      datos_tecnicos=[DatoTecnico("espera", "21 dias", "fraguar durante 21 días", 1)],
                      caracteristicas=["Voltaje: 220 V"]),
            EspecItem(numero=99, titulo="NO EXISTE", unidad_spec=None, modulo_spec=None, pagina_inicio=2),
        ])

    def test_especificaciones_se_asignan_por_numero_y_el_b1_no_cambia(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        srv.guardar_especificaciones(self.db, p, self._esp_demo(), "esp.pdf")
        out = srv.a_proyecto_out(p)
        it1 = out.modulos[0].items[0]
        self.assertTrue(it1.tiene_especificacion)
        self.assertEqual([r.nombre for r in it1.requisitos], ["Peón"])
        self.assertEqual(it1.requisitos[0].estado, "pendiente")
        self.assertEqual(it1.caracteristicas, ["Voltaje: 220 V"])
        self.assertEqual(it1.datos_tecnicos[0].valor, "21 dias")
        self.assertFalse(out.modulos[0].items[1].tiene_especificacion)
        self.assertEqual(out.items_con_especificacion, 1)
        codigos = {(a.codigo, a.origen) for a in out.alertas}
        self.assertIn(("especificacion_sin_item", "especificaciones"), codigos)  # ítem 99
        self.assertIn(("item_sin_especificacion", "especificaciones"), codigos)  # ítems 2 y 3
        self.assertEqual((it1.descripcion, it1.unidad, it1.cantidad_texto), ("RETIRO DE CIELO", "m²", "32,34"))

    def test_volver_a_importar_reemplaza_lo_anterior(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        srv.guardar_especificaciones(self.db, p, self._esp_demo(), "esp.pdf")
        srv.guardar_especificaciones(self.db, p, self._esp_demo(), "esp.pdf")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(models.RequisitoRecurso)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(models.EspecificacionItem)), 1)
        self.assertEqual(sum(1 for a in p.alertas if a.codigo == "especificacion_sin_item"), 1)
        self.assertEqual(sum(1 for a in p.alertas if a.origen == "b1"), 1)  # las del B-1 se conservan

    def test_borrar_proyecto_borra_tambien_las_especificaciones(self):
        p = srv.crear_desde_b1(self.db, _resultado_demo(), "Demo", None)
        srv.guardar_especificaciones(self.db, p, self._esp_demo(), "esp.pdf")
        self.db.delete(p)
        self.db.commit()
        for modelo in (models.EspecificacionItem, models.RequisitoRecurso, models.DatoTecnicoItem, models.Item):
            self.assertEqual(self.db.scalar(select(func.count()).select_from(modelo)), 0, modelo.__name__)

    @unittest.skipUnless(PDF_REAL.exists() and ESP_REAL.exists(), "Faltan los PDF reales.")
    def test_b1_y_especificaciones_reales(self):
        p = srv.crear_desde_b1(self.db, parse_b1(PDF_REAL), "San Pedro", PDF_REAL.name)
        srv.guardar_especificaciones(self.db, p, parse_especificaciones(ESP_REAL), ESP_REAL.name)
        out = srv.a_proyecto_out(p)
        self.assertEqual((out.total_items, out.items_con_especificacion), (24, 24))
        self.assertEqual(sum(len(i.requisitos) for m in out.modulos for i in m.items), 95)
        item5 = [i for m in out.modulos for i in m.items if i.numero == 5][0]
        self.assertEqual((item5.unidad, item5.sin_materiales), ("m³", True))  # manda el B-1
        avisos = {(a.codigo, a.item_numero) for a in out.alertas if a.origen == "especificaciones"}
        self.assertIn(("unidad_distinta", 5), avisos)
        self.assertIn(("unidad_sospechosa", 17), avisos)


if __name__ == "__main__":
    unittest.main()
