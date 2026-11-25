"""Importa una biblioteca de APU desde Excel: UNA FILA POR LÍNEA de cada APU.

Columnas (el orden no importa; los nombres se reconocen con variantes):
  APU | Unidad del APU | Tipo | Recurso | Unidad | Cantidad | Precio unitario | Origen del rendimiento | Código
- Si la celda "APU" está vacía, la fila sigue en el APU anterior (como en una planilla con celdas combinadas).
- Tipo: material, mano de obra o equipo.
- Cantidad = consumo o rendimiento por unidad del APU (p. ej. kg de cemento por m²).
Nada se corrige en silencio: lo dudoso se reporta como alerta con su número de fila.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from .b1_parser import _clave, normalizar_unidad, parse_cantidad


@dataclass
class AlertaFila:
    nivel: str  # error | advertencia | info
    codigo: str
    mensaje: str
    fila: Optional[int] = None


@dataclass
class LineaImportada:
    tipo: str
    recurso: str
    unidad: str
    cantidad: Optional[Decimal]
    precio_unitario: Optional[Decimal]
    origen_rendimiento: str
    fila: int


@dataclass
class ApuImportado:
    nombre: str
    unidad: str
    codigo: Optional[str]
    fila: int
    lineas: list[LineaImportada] = field(default_factory=list)

    @property
    def unidad_normalizada(self) -> str:
        return normalizar_unidad(self.unidad)


@dataclass
class ResultadoBiblioteca:
    apus: list[ApuImportado] = field(default_factory=list)
    alertas: list[AlertaFila] = field(default_factory=list)
    hoja: str = ""

    @property
    def total_lineas(self) -> int:
        return sum(len(a.lineas) for a in self.apus)

    @property
    def hay_errores(self) -> bool:
        return any(a.nivel == "error" for a in self.alertas)


COLUMNAS = ["APU", "Unidad del APU", "Tipo", "Recurso", "Unidad", "Cantidad", "Precio unitario",
            "Origen del rendimiento", "Código"]

_ALIAS = {
    "apu": ["apu", "nombredelapu", "analisis", "descripciondelapu", "item", "partida"],
    "unidad_apu": ["unidaddelapu", "unidadapu", "unidaddelitem", "unidaditem", "unidadpartida"],
    "tipo": ["tipo", "tipoderecurso", "categoria", "clase"],
    "recurso": ["recurso", "insumo", "componente", "descripciondelrecurso", "detalle", "material"],
    "unidad": ["unidad", "unidadrecurso", "unidaddelrecurso", "und", "unid"],
    "cantidad": ["cantidad", "cant", "rendimiento", "consumo", "incidencia"],
    "precio": ["preciounitario", "precio", "pu", "costounitario", "costo"],
    "origen": ["origendelrendimiento", "origenrendimiento", "origen", "fuente"],
    "codigo": ["codigo", "cod", "codigoapu"],
}
_TIPOS = {
    "material": "material", "materiales": "material", "mat": "material",
    "manodeobra": "mano_obra", "mo": "mano_obra", "obra": "mano_obra", "personal": "mano_obra",
    "equipo": "equipo", "equipos": "equipo", "maquinaria": "equipo", "herramienta": "equipo",
    "herramientas": "equipo", "equipoymaquinaria": "equipo", "equipomaquinaria": "equipo",
}
_ORIGENES = {"biblioteca", "medido", "calculado", "similar", "comunitario", "referencial", "manual"}


def _texto(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _numero(v: Any) -> tuple[Optional[Decimal], bool]:
    """(valor, legible). Una celda vacía es (None, True); un texto ilegible es (None, False)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, True
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v)), True  # str() evita los artefactos binarios del float
    n = parse_cantidad(str(v))
    return n, n is not None


def _detectar_cabecera(filas: list[tuple[int, list[Any]]]) -> Optional[tuple[int, dict[str, int]]]:
    for nfila, celdas in filas[:20]:
        encontrado: dict[str, int] = {}
        for idx, c in enumerate(celdas):
            k = _clave(_texto(c))
            if not k:
                continue
            for campo, alias in _ALIAS.items():
                if k in alias and campo not in encontrado:
                    encontrado[campo] = idx
                    break
        # "Unidad" sola, cuando existe "Unidad del APU", es la unidad del recurso (ya queda así por el orden de alias)
        if "recurso" in encontrado and "cantidad" in encontrado and "apu" in encontrado:
            return nfila, encontrado
    return None


def leer_biblioteca_excel(fuente: Union[str, Path, BinaryIO, bytes]) -> ResultadoBiblioteca:
    from openpyxl import load_workbook  # import perezoso

    res = ResultadoBiblioteca()
    if isinstance(fuente, (bytes, bytearray)):
        fuente = io.BytesIO(fuente)
    try:
        libro = load_workbook(fuente, data_only=True, read_only=True)
    except Exception as exc:
        res.alertas.append(AlertaFila("error", "archivo_ilegible", f"No se pudo abrir el Excel (.xlsx): {exc}"))
        return res
    hoja = libro["Biblioteca"] if "Biblioteca" in libro.sheetnames else libro[libro.sheetnames[0]]
    res.hoja = hoja.title
    filas = [(i, list(r)) for i, r in enumerate(hoja.iter_rows(values_only=True), start=1)]
    cab = _detectar_cabecera(filas)
    if cab is None:
        res.alertas.append(AlertaFila(
            "error", "sin_encabezado",
            "No se encontró la fila de encabezados. Se esperan al menos las columnas APU, Recurso y Cantidad "
            "(descarga la plantilla para ver el formato)."))
        return res
    n_cab, col = cab

    def celda(fila: list[Any], campo: str) -> Any:
        i = col.get(campo)
        return fila[i] if i is not None and i < len(fila) else None

    actual: Optional[ApuImportado] = None
    for nfila, fila in filas:
        if nfila <= n_cab or not any(_texto(c) for c in fila):
            continue
        nombre = _texto(celda(fila, "apu"))
        if nombre and (actual is None or _clave(nombre) != _clave(actual.nombre) or _texto(celda(fila, "codigo")) not in ("", actual.codigo or "")):
            actual = ApuImportado(nombre=nombre, unidad="", codigo=_texto(celda(fila, "codigo")) or None, fila=nfila)
            res.apus.append(actual)
        if actual is None:
            res.alertas.append(AlertaFila("error", "fila_sin_apu", "Fila sin APU: no hay un APU anterior al que pertenezca.", nfila))
            continue
        unidad_apu = _texto(celda(fila, "unidad_apu"))
        if unidad_apu and not actual.unidad:
            actual.unidad = unidad_apu

        recurso = _texto(celda(fila, "recurso"))
        tipo_txt = _texto(celda(fila, "tipo"))
        if not recurso and not tipo_txt and celda(fila, "cantidad") is None:
            continue  # fila que solo repite/define el APU
        if not recurso:
            res.alertas.append(AlertaFila("error", "sin_recurso", f"Falta el nombre del recurso en el APU '{actual.nombre}'.", nfila))
            continue
        tipo = _TIPOS.get(_clave(tipo_txt))
        if tipo is None:
            res.alertas.append(AlertaFila(
                "error", "tipo_desconocido",
                f"Tipo '{tipo_txt}' no reconocido en '{recurso}' (usa material, mano de obra o equipo). Fila omitida.", nfila))
            continue
        cantidad, ok_c = _numero(celda(fila, "cantidad"))
        precio, ok_p = _numero(celda(fila, "precio"))
        if not ok_c:
            res.alertas.append(AlertaFila("advertencia", "cantidad_ilegible", f"Cantidad ilegible en '{recurso}': queda pendiente.", nfila))
        if not ok_p:
            res.alertas.append(AlertaFila("advertencia", "precio_ilegible", f"Precio ilegible en '{recurso}': queda pendiente.", nfila))
        if (cantidad is not None and cantidad < 0) or (precio is not None and precio < 0):
            res.alertas.append(AlertaFila("error", "valor_negativo", f"Valor negativo en '{recurso}'. Fila omitida.", nfila))
            continue
        origen = _clave(_texto(celda(fila, "origen"))) or "biblioteca"
        if origen not in _ORIGENES:
            res.alertas.append(AlertaFila("advertencia", "origen_desconocido",
                                          f"Origen del rendimiento '{_texto(celda(fila, 'origen'))}' no reconocido; se usa 'manual'.", nfila))
            origen = "manual"
        actual.lineas.append(LineaImportada(tipo, recurso, _texto(celda(fila, "unidad")), cantidad, precio, origen, nfila))

    vistos: dict[str, int] = {}
    for a in res.apus:
        if not a.lineas:
            res.alertas.append(AlertaFila("advertencia", "apu_sin_lineas", f"El APU '{a.nombre}' no tiene recursos.", a.fila))
        if not a.unidad:
            res.alertas.append(AlertaFila("info", "apu_sin_unidad",
                                          f"El APU '{a.nombre}' no tiene unidad; no se podrá comprobar contra la unidad del B-1.", a.fila))
        k = _clave(a.nombre) + "|" + normalizar_unidad(a.unidad)
        if k in vistos:
            res.alertas.append(AlertaFila("advertencia", "apu_repetido",
                                          f"El APU '{a.nombre}' ya apareció en la fila {vistos[k]}. Se importan ambos.", a.fila))
        vistos.setdefault(k, a.fila)
    return res


# ---- plantilla descargable -------------------------------------------------------------------------

_EJEMPLO = [
    ("RETIRO DE CIELO RASO DE YESO", "m2", "Mano de obra", "Peón", "h", 0.8, 20, "biblioteca", "A-001"),
    ("RETIRO DE CIELO RASO DE YESO", "m2", "Equipo", "Herramientas menores", "%", 0.05, 16, "biblioteca", None),
    ("CONTRAPISO DE HORMIGON E=5 CM + EMPEDRADO", "m2", "Material", "Cemento portland", "kg", 17.5, 1.3, "calculado", "A-002"),
    (None, None, "Material", "Arena común", "m3", 0.03, 150, "calculado", None),
    (None, None, "Material", "Grava común", "m3", 0.04, 170, "calculado", None),
    (None, None, "Material", "Piedra manzana", "m3", 0.05, 160, "biblioteca", None),
    (None, None, "Mano de obra", "Albañil", "h", 0.6, 30, "biblioteca", None),
    (None, None, "Mano de obra", "Ayudante", "h", 0.6, 20, "biblioteca", None),
    (None, None, "Equipo", "Mezcladora", "h", 0.15, 25, "biblioteca", None),
]


def crear_plantilla_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Biblioteca"
    ws.append(COLUMNAS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1D4F91")
    for fila in _EJEMPLO:
        ws.append(list(fila))
    for i, ancho in enumerate([46, 14, 16, 30, 10, 12, 16, 22, 12], start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "A2"

    info = wb.create_sheet("Instrucciones")
    for linea in [
        "Una fila por cada recurso de cada APU.",
        "Si la celda APU está vacía, la fila sigue en el APU de arriba.",
        "Tipo: Material, Mano de obra o Equipo.",
        "Cantidad: consumo o rendimiento POR UNIDAD DEL APU (por ejemplo, kg de cemento por m²).",
        "Origen del rendimiento (opcional): biblioteca, medido, calculado, similar, referencial o manual.",
        "Usa coma o punto para los decimales. Los precios son en bolivianos.",
        "Los valores de las filas de ejemplo son solo ilustrativos: reemplázalos por los tuyos.",
    ]:
        info.append([linea])
    info.column_dimensions["A"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Lee una biblioteca de APU en Excel, o crea la plantilla.")
    ap.add_argument("xlsx", nargs="?")
    ap.add_argument("--plantilla", help="crear la plantilla en esta ruta")
    args = ap.parse_args(argv)
    if args.plantilla:
        Path(args.plantilla).write_bytes(crear_plantilla_bytes())
        print("Plantilla creada:", args.plantilla)
        return 0
    if not args.xlsx:
        ap.error("indica un .xlsx o usa --plantilla")
    r = leer_biblioteca_excel(args.xlsx)
    print(f"Hoja '{r.hoja}': {len(r.apus)} APU, {r.total_lineas} líneas")
    for a in r.apus:
        print(f"  {a.nombre} [{a.unidad}] — {len(a.lineas)} líneas")
    for al in r.alertas:
        print(f"  [{al.nivel}] fila {al.fila}: {al.mensaje}")
    return 1 if r.hay_errores else 0


if __name__ == "__main__":
    raise SystemExit(_main())
