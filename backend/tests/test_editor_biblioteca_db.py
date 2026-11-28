import importlib.util
import unittest

HAY = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "fastapi", "httpx"))
if HAY:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.db.session import get_db
    from app.importers.biblioteca_excel import ApuImportado, LineaImportada, ResultadoBiblioteca
    from app.main import app
    from app.services import bibliotecas as bib
    from app.services import unidades


@unittest.skipUnless(HAY, "Faltan dependencias.")
class Base_(unittest.TestCase):
    def setUp(self):
        e = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(e)
        self.S = sessionmaker(bind=e, expire_on_commit=False)
        with self.S() as db:
            unidades.sembrar(db)

        def get_db_():
            db = self.S()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = get_db_
        self.c = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def bib(self, nombre="Mi biblioteca"):
        return self.c.post("/bibliotecas", json={"nombre": nombre}).json()["id"]

    def item(self, bid, nombre="MURO DE LADRILLO", unidad="m2", **kw):
        return self.c.post(f"/bibliotecas/{bid}/apus", json={"nombre": nombre, "unidad": unidad, **kw}).json()

    def linea(self, aid, **kw):
        return self.c.post(f"/bibliotecas/apus/{aid}/lineas", json=kw)


class TestUnidades(Base_):
    def test_predefinidas_por_tipo_y_sembrado_repetible(self):
        mat = [u["simbolo"] for u in self.c.get("/unidades", params={"tipo": "material"}).json()]
        for esperado in ("Kg", "Pza", "Glb", "Rollo", "m"):
            self.assertIn(esperado, mat)
        self.assertIn("Hr", [u["simbolo"] for u in self.c.get("/unidades", params={"tipo": "mano_obra"}).json()])
        self.assertIn("Hr", [u["simbolo"] for u in self.c.get("/unidades", params={"tipo": "equipo"}).json()])
        with self.S() as db:
            self.assertEqual(unidades.sembrar(db), 0)

    def test_agregar_una_propia_sin_duplicar_ni_borrar_predefinidas(self):
        r = self.c.post("/unidades", json={"tipo": "mano_obra", "simbolo": "Turno"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.post("/unidades", json={"tipo": "mano_obra", "simbolo": "turno"}).status_code, 422)
        self.assertEqual(self.c.post("/unidades", json={"tipo": "mano_obra", "simbolo": "hr"}).status_code, 422)  # ya existe (Hr)
        self.assertEqual(self.c.post("/unidades", json={"tipo": "xx", "simbolo": "a"}).status_code, 422)
        predef = next(u for u in self.c.get("/unidades", params={"tipo": "material"}).json() if u["simbolo"] == "Kg")
        self.assertEqual(self.c.delete(f"/unidades/{predef['id']}").status_code, 422)
        self.assertEqual(self.c.delete(f"/unidades/{r.json()['id']}").status_code, 204)

    def test_lo_que_se_escribe_se_unifica_o_se_agrega(self):
        with self.S() as db:
            self.assertEqual(unidades.resolver(db, "material", "kg"), "Kg")
            self.assertEqual(unidades.resolver(db, "material", "pie2"), "P2")
            self.assertEqual(unidades.resolver(db, "material", "Bolsa 50 kg"), "Bolsa 50 kg")
            db.commit()
            self.assertIn("Bolsa 50 kg", [u.simbolo for u in unidades.listar(db, "material")])
            self.assertEqual(unidades.resolver(db, "material", "  "), "")
            with self.assertRaises(ValueError):
                unidades.resolver(db, "material", "x" * 21)


class TestEditor(Base_):
    def test_biblioteca_desde_cero_y_renombrar(self):
        bid = self.bib("Mi obra")
        r = self.c.patch(f"/bibliotecas/{bid}", json={"nombre": "Mi base 2027"})
        self.assertEqual(r.json()["nombre"], "Mi base 2027")
        self.assertEqual(self.c.post("/bibliotecas", json={"nombre": "  "}).status_code, 422)

    def test_grupos_anidados_sin_ciclos_y_borrar_no_pierde_items(self):
        bid = self.bib()
        g1 = self.c.post(f"/bibliotecas/{bid}/grupos", json={"nombre": "Obra gruesa"}).json()
        g2 = self.c.post(f"/bibliotecas/{bid}/grupos", json={"nombre": "Muros", "padre_id": g1["id"]}).json()
        a = self.item(bid, grupo_id=g2["id"])
        self.assertEqual(a["grupo_id"], g2["id"])
        # un grupo no puede quedar dentro de su propio subgrupo
        self.assertEqual(self.c.patch(f"/bibliotecas/grupos/{g1['id']}", json={"padre_id": g2["id"]}).status_code, 422)
        self.assertEqual(self.c.patch(f"/bibliotecas/grupos/{g1['id']}", json={"padre_id": g1["id"]}).status_code, 422)
        listado = {g["id"]: g for g in self.c.get(f"/bibliotecas/{bid}/grupos").json()}
        self.assertEqual(listado[g2["id"]]["items"], 1)
        # borrar «Muros»: el ítem queda sin grupo (no se borra); borrar el padre sube los hijos
        self.assertEqual(self.c.delete(f"/bibliotecas/grupos/{g2['id']}").status_code, 204)
        self.assertIsNone(self.c.get(f"/bibliotecas/apus/{a['id']}").json()["grupo_id"])
        g3 = self.c.post(f"/bibliotecas/{bid}/grupos", json={"nombre": "Hijo", "padre_id": g1["id"]}).json()
        self.c.delete(f"/bibliotecas/grupos/{g1['id']}")
        self.assertIsNone({g["id"]: g for g in self.c.get(f"/bibliotecas/{bid}/grupos").json()}[g3["id"]]["padre_id"])
        # un grupo de otra biblioteca no sirve
        otra = self.bib("Otra")
        self.assertEqual(self.c.post(f"/bibliotecas/{otra}/apus", json={"nombre": "X", "grupo_id": g3["id"]}).status_code, 404)

    def test_item_con_unidad_unificada(self):
        bid = self.bib()
        a = self.item(bid, unidad="M2")
        self.assertEqual(a["unidad"], "m2")
        a2 = self.c.patch(f"/bibliotecas/apus/{a['id']}", json={"unidad": "m3", "nombre": "MURO DE LADRILLO 15"}).json()
        self.assertEqual((a2["unidad"], a2["nombre"]), ("m3", "MURO DE LADRILLO 15"))
        self.assertEqual(self.c.post(f"/bibliotecas/{bid}/apus", json={"nombre": ""}).status_code, 422)
        self.assertEqual(self.item(bid, nombre="Sin unidad", unidad="")["unidad"], "")  # se permite y queda por completar

    def test_escribir_un_recurso_libremente_lo_agrega_a_la_biblioteca_con_su_unidad(self):
        bid = self.bib()
        a = self.item(bid)
        r = self.linea(a["id"], tipo="material", nombre="Ladrillo 6H", unidad="pza", cantidad=40, precio_unitario="1.2")
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertEqual(d["lineas"][0]["unidad"], "Pza")  # unificada con el catálogo
        self.assertTrue(any("Ladrillo 6H" in v for v in d["avisos"]))
        recursos = self.c.get(f"/bibliotecas/{bid}/recursos", params={"tipo": "material"}).json()
        self.assertEqual([(x["nombre"], x["unidad"], x["usos"]) for x in recursos], [("Ladrillo 6H", "Pza", 1)])
        self.assertEqual(recursos[0]["precio_referencia"], "1.2")
        # una unidad inventada queda en «mis unidades»
        self.linea(a["id"], tipo="material", nombre="Pegamento", unidad="Cubeta 20L", cantidad=1, precio_unitario=100)
        self.assertIn("Cubeta 20L", [u["simbolo"] for u in self.c.get("/unidades", params={"tipo": "material"}).json()])
        # costo directo = 40 × 1,2 + 1 × 100
        self.assertEqual(self.c.get(f"/bibliotecas/apus/{a['id']}").json()["costo_directo"], "148.00")

    def test_elegir_de_la_biblioteca_hereda_el_precio_y_no_duplica(self):
        bid = self.bib()
        a, b = self.item(bid), self.item(bid, nombre="REVOQUE", unidad="m2")
        self.linea(a["id"], tipo="mano_obra", nombre="Albañil", unidad="Hr", cantidad=1, precio_unitario=23)
        rid = self.c.get(f"/bibliotecas/{bid}/recursos").json()[0]["id"]
        d = self.linea(b["id"], recurso_id=rid, cantidad="0.5").json()
        self.assertEqual((d["lineas"][0]["precio_unitario"], d["lineas"][0]["importe"]), ("23", "11.50"))
        self.assertEqual(d["avisos"], [])
        # escribirlo otra vez igual (otras mayúsculas) reutiliza el recurso
        self.linea(b["id"], tipo="mano_obra", nombre="ALBAÑIL", unidad="hr", cantidad=1)
        self.assertEqual(len(self.c.get(f"/bibliotecas/{bid}/recursos").json()), 1)
        self.assertEqual(self.c.get(f"/bibliotecas/{bid}/recursos").json()[0]["usos"], 3)

    def test_mismo_nombre_con_otra_unidad_se_avisa_y_queda_aparte(self):
        bid = self.bib()
        a = self.item(bid)
        self.linea(a["id"], tipo="material", nombre="Cemento", unidad="Kg", cantidad=7, precio_unitario="1.92")
        d = self.linea(a["id"], tipo="material", nombre="Cemento", unidad="Bolsa", cantidad=1, precio_unitario=96).json()
        self.assertTrue(any("otra unidad" in v for v in d["avisos"]))
        self.assertEqual(len(self.c.get(f"/bibliotecas/{bid}/recursos").json()), 2)

    def test_crear_recursos_sin_item_y_duplicado(self):
        bid = self.bib()
        r = self.c.post(f"/bibliotecas/{bid}/recursos", json={"tipo": "equipo", "nombre": "Mezcladora", "unidad": "Hr", "precio_referencia": 25})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.post(f"/bibliotecas/{bid}/recursos", json={"tipo": "equipo", "nombre": "mezcladora", "unidad": "hr"}).status_code, 422)
        self.assertEqual(self.c.post(f"/bibliotecas/{bid}/recursos", json={"tipo": "otro", "nombre": "x", "unidad": "u"}).status_code, 422)
        self.assertEqual(self.c.post(f"/bibliotecas/{bid}/recursos", json={"tipo": "material", "nombre": "x", "unidad": "Kg", "precio_referencia": -1}).status_code, 422)

    def test_cambiar_un_recurso_se_propaga_a_los_items_de_la_biblioteca(self):
        bid = self.bib()
        a = self.item(bid)
        self.linea(a["id"], tipo="material", nombre="Arena", unidad="m3", cantidad="0.04", precio_unitario=194)
        r = self.c.get(f"/bibliotecas/{bid}/recursos").json()[0]
        self.c.patch(f"/bibliotecas/recursos/{r['id']}", json={"nombre": "Arena común", "precio_referencia": 200})
        l = self.c.get(f"/bibliotecas/apus/{a['id']}").json()["lineas"][0]
        self.assertEqual((l["descripcion"], l["precio_unitario"], l["importe"]), ("Arena común", "200", "8.00"))
        self.c.patch(f"/bibliotecas/recursos/{r['id']}", json={"unidad": "Viaje"})  # solo la unidad: el precio no se toca
        l = self.c.get(f"/bibliotecas/apus/{a['id']}").json()["lineas"][0]
        self.assertEqual((l["unidad"], l["precio_unitario"]), ("Viaje", "200"))

    def test_borrar_un_recurso_en_uso_pide_confirmacion(self):
        bid = self.bib()
        a = self.item(bid)
        self.linea(a["id"], tipo="material", nombre="Arena", unidad="m3", cantidad=1, precio_unitario=1)
        rid = self.c.get(f"/bibliotecas/{bid}/recursos").json()[0]["id"]
        self.assertEqual(self.c.delete(f"/bibliotecas/recursos/{rid}").status_code, 422)
        self.assertEqual(self.c.delete(f"/bibliotecas/recursos/{rid}", params={"forzar": True}).status_code, 204)
        l = self.c.get(f"/bibliotecas/apus/{a['id']}").json()["lineas"][0]
        self.assertEqual((l["descripcion"], l["recurso_id"]), ("Arena", None))  # la línea conserva su texto

    def test_traer_un_recurso_de_otra_biblioteca(self):
        origen, destino = self.bib("Origen"), self.bib("Destino")
        a = self.item(origen)
        self.linea(a["id"], tipo="material", nombre="Cemento portland", unidad="Kg", cantidad=7, precio_unitario="1.92")
        hallados = self.c.get(f"/bibliotecas/{destino}/recursos-de-otras", params={"q": "cemento"}).json()
        self.assertEqual([(h["nombre"], h["biblioteca_nombre"]) for h in hallados], [("Cemento portland", "Origen")])
        copia = self.c.post(f"/bibliotecas/{destino}/recursos/copiar", json={"recurso_id": hallados[0]["id"]}).json()
        self.assertEqual((copia["unidad"], copia["precio_referencia"]), ("Kg", "1.92"))
        otra = self.c.post(f"/bibliotecas/{destino}/recursos/copiar", json={"recurso_id": hallados[0]["id"]}).json()
        self.assertEqual(otra["id"], copia["id"])  # no se duplica
        # una línea no puede usar un recurso de otra biblioteca sin copiarlo antes
        b = self.item(destino)
        self.assertEqual(self.linea(b["id"], recurso_id=hallados[0]["id"], cantidad=1).status_code, 404)

    def test_editar_y_borrar_lineas_y_duplicar_item(self):
        bid = self.bib()
        a = self.item(bid)
        self.linea(a["id"], tipo="mano_obra", nombre="Peón", unidad="Hr", cantidad=1, precio_unitario=17)
        lid = self.c.get(f"/bibliotecas/apus/{a['id']}").json()["lineas"][0]["id"]
        d = self.c.patch(f"/bibliotecas/lineas/{lid}", json={"cantidad": "0.8", "origen_rendimiento": "medido"}).json()
        self.assertEqual((d["lineas"][0]["cantidad"], d["lineas"][0]["origen_rendimiento"], d["costo_directo"]), ("0.8", "medido", "13.60"))
        self.assertEqual(self.c.patch(f"/bibliotecas/lineas/{lid}", json={"cantidad": -2}).status_code, 422)
        self.assertEqual(self.c.patch(f"/bibliotecas/lineas/{lid}", json={"origen_rendimiento": "inventado"}).status_code, 422)
        copia = self.c.post(f"/bibliotecas/apus/{a['id']}/duplicar").json()
        self.assertTrue(copia["nombre"].endswith("(copia)"))
        self.assertEqual(copia["costo_directo"], "13.60")
        self.assertEqual(self.c.delete(f"/bibliotecas/lineas/{lid}").json()["lineas"], [])
        self.assertEqual(self.c.get(f"/bibliotecas/apus/{copia['id']}").json()["costo_directo"], "13.60")  # la copia no se ve afectada

    def test_linea_sin_cantidad_deja_el_item_incompleto(self):
        bid = self.bib()
        a = self.item(bid)
        d = self.linea(a["id"], tipo="material", nombre="Clavos", unidad="Kg", precio_unitario=15).json()
        self.assertIsNone(d["costo_directo"])  # nunca se inventa un costo
        self.assertEqual(self.c.post(f"/bibliotecas/apus/{a['id']}/lineas", json={"tipo": "material", "nombre": "x", "unidad": "Kg", "origen_rendimiento": "xx"}).status_code, 422)

    def test_importar_registra_unidades_sin_cambiar_el_texto(self):
        res = ResultadoBiblioteca(apus=[ApuImportado(nombre="ITEM", unidad="M2", codigo=None, fila=2, lineas=[
            LineaImportada("material", "Lámina", "Plancha 2x1", 1, 10, "biblioteca", 2)])], hoja="x")
        with self.S() as db:
            b = bib.crear_desde_excel(db, "Importada", res)
            self.assertEqual((b.apus[0].unidad, b.apus[0].lineas[0].unidad), ("M2", "Plancha 2x1"))  # texto original intacto
            self.assertIn("Plancha 2x1", [u.simbolo for u in unidades.listar(db, "material")])


if __name__ == "__main__":
    unittest.main()
