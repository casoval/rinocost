"""Exporta el proyecto a Excel: Formulario B-1 con precios y literal, resumen por módulo, análisis de precios
unitarios, lista consolidada de recursos y (opcional) cronograma con diagrama de barras.

Los totales son FÓRMULAS vivas de Excel: si cambias una cantidad o un precio en el archivo, se recalculan.
Recibe diccionarios (la salida JSON del proyecto y del cronograma), no objetos de base de datos.
"""
from __future__ import annotations

import io
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..importers.b1_parser import normalizar_unidad
from ..matching import preparar
from .letras import numero_a_letras

AZUL, AZUL_SUAVE, GRIS = "1D4F91", "E4ECF6", "F2F2F2"
_LADO = Side(style="thin", color="BFBFBF")
_BORDE = Border(left=_LADO, right=_LADO, top=_LADO, bottom=_LADO)
_DINERO = "#,##0.00"
_TIPO = {"material": "Material", "mano_obra": "Mano de obra", "equipo": "Equipo"}
_ORDEN_TIPO = {"material": 0, "mano_obra": 1, "equipo": 2}
_ORIGEN_DATO = {"pliego": "Pliego", "biblioteca": "Mi biblioteca", "ambos": "Pliego + biblioteca", "manual": "Agregado manualmente"}
_ORIGEN_REND = {"manual": "Manual", "medido": "Medido en obra", "calculado": "Calculado", "similar": "De un ítem similar",
                "referencial": "Referencial", "biblioteca": "Mi biblioteca", "comunitario": "Comunitario",
                "pendiente": "Pendiente"}


def _f(v: Optional[str]) -> Optional[float]:
    return None if v is None else float(v)


def _cabecera(ws, fila: int, titulos: list[str]) -> None:
    for i, t in enumerate(titulos, start=1):
        c = ws.cell(fila, i, t)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _BORDE


def _banda(ws, fila: int, texto: str, columnas: int) -> None:
    ws.cell(fila, 1, texto)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=columnas)
    c = ws.cell(fila, 1)
    c.font = Font(bold=True, color=AZUL)
    c.fill = PatternFill("solid", fgColor=AZUL_SUAVE)


def _anchos(ws, anchos: list[float]) -> None:
    for i, a in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = a


def _hoja_b1(wb: Workbook, p: dict) -> dict[int, tuple[int, int]]:
    ws = wb.active
    ws.title = "Formulario B-1"
    ws["A1"] = "FORMULARIO B-1"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "PRESUPUESTO POR ÍTEMS Y GENERAL DE LA OBRA (En bolivianos)"
    ws["A3"] = f"Proyecto: {p['nombre']}"
    _cabecera(ws, 5, ["Ítem", "Descripción", "Unidad", "Cantidad", "Precio Unitario (Numeral)",
                      "Precio Unitario (Literal)", "Precio Total (Numeral)"])
    ws.row_dimensions[5].height = 32
    r, rangos = 6, {}
    for m in p["modulos"]:
        _banda(ws, r, f"> {m['codigo']} - {m['nombre']}", 7)
        r += 1
        primera = r
        for it in m["items"]:
            ws.cell(r, 1, it["numero"])
            ws.cell(r, 2, it["descripcion"]).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(r, 3, it["unidad"])
            cantidad = _f(it.get("cantidad"))
            ws.cell(r, 4, cantidad if cantidad is not None else it["cantidad_texto"]).number_format = _DINERO
            pu = _f(it.get("precio_unitario"))
            if pu is not None:
                ws.cell(r, 5, pu)
                ws.cell(r, 6, numero_a_letras(Decimal(it["precio_unitario"]))).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(r, 5).number_format = _DINERO
            ws.cell(r, 7, f'=IF(ISNUMBER(E{r}),ROUND(D{r}*E{r},2),"")').number_format = _DINERO
            for c in range(1, 8):
                ws.cell(r, c).border = _BORDE
            r += 1
        rangos[m["id"]] = (primera, r - 1)
    ws.cell(r + 1, 6, "PRECIO TOTAL (Numeral)").font = Font(bold=True)
    total = ws.cell(r + 1, 7, f"=SUM(G6:G{max(r - 1, 6)})")  # hasta la última fila de ítems
    total.font, total.number_format = Font(bold=True), _DINERO
    ws.cell(r + 3, 1, "El precio en letras se genera al exportar: si cambias un precio en Excel, actualiza su literal.").font = Font(italic=True, color="7F7F7F")
    _anchos(ws, [7, 62, 10, 12, 18, 34, 18])
    ws.freeze_panes = "A6"
    return rangos


def _hoja_resumen(wb: Workbook, p: dict, rangos: dict[int, tuple[int, int]]) -> None:
    ws = wb.create_sheet("Resumen")
    ws["A1"] = "RESUMEN POR MÓDULO"
    ws["A1"].font = Font(bold=True, size=14)
    _cabecera(ws, 3, ["Módulo", "Nombre", "Ítems", "Ítems con precio", "Total (Bs)"])
    r = 4
    for m in p["modulos"]:
        a, b = rangos[m["id"]]
        ws.cell(r, 1, m["codigo"])
        ws.cell(r, 2, m["nombre"])
        ws.cell(r, 3, len(m["items"]))
        ws.cell(r, 4, f"=COUNT('Formulario B-1'!E{a}:E{b})" if a <= b else 0)
        ws.cell(r, 5, f"=SUM('Formulario B-1'!G{a}:G{b})" if a <= b else 0).number_format = _DINERO
        for c in range(1, 6):
            ws.cell(r, c).border = _BORDE
        r += 1
    ws.cell(r, 2, "TOTAL").font = Font(bold=True)
    ws.cell(r, 3, f"=SUM(C4:C{r - 1})").font = Font(bold=True)
    ws.cell(r, 4, f"=SUM(D4:D{r - 1})").font = Font(bold=True)
    t = ws.cell(r, 5, f"=SUM(E4:E{r - 1})")
    t.font, t.number_format = Font(bold=True), _DINERO
    ws.cell(r + 2, 1, "Los precios unitarios incluyen los costos indirectos del modelo de cálculo del proyecto (ver «Análisis de precios»).").font = Font(italic=True, color="7F7F7F")
    _anchos(ws, [10, 46, 10, 16, 18])


def _hoja_apu(wb: Workbook, p: dict) -> None:
    ws = wb.create_sheet("Análisis de precios")
    ws["A1"] = "ANÁLISIS DE PRECIOS UNITARIOS"
    ws["A1"].font = Font(bold=True, size=14)
    r = 3
    for m in p["modulos"]:
        for it in m["items"]:
            apu = it.get("apu")
            if not apu:
                continue
            _banda(ws, r, f"ÍTEM {it['numero']} — {it['descripcion']}   [{it['unidad']}]", 8)
            r += 1
            _cabecera(ws, r, ["Tipo", "Recurso", "Unidad", "Cantidad por unidad del ítem", "Precio (Bs)", "Parcial (Bs)",
                              "Origen del rendimiento", "Origen del recurso"])
            ws.row_dimensions[r].height = 32
            r += 1
            primera = r
            for l in apu["lineas"]:
                ws.cell(r, 1, _TIPO.get(l["tipo"], l["tipo"]))
                ws.cell(r, 2, l["descripcion"])
                ws.cell(r, 3, l["unidad"])
                cant, pre = _f(l["cantidad"]), _f(l["precio_unitario"])
                ws.cell(r, 4, cant if cant is not None else "pendiente").number_format = "#,##0.0000"
                ws.cell(r, 5, pre if pre is not None else "pendiente").number_format = _DINERO
                ws.cell(r, 6, f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),D{r}*E{r},"")').number_format = _DINERO
                ws.cell(r, 7, _ORIGEN_REND.get(l["origen_rendimiento"], l["origen_rendimiento"]))
                ws.cell(r, 8, _ORIGEN_DATO.get(l["origen_dato"], l["origen_dato"]) + (" (lo pide el pliego)" if l["requerido_por_pliego"] else ""))
                for c in range(1, 9):
                    ws.cell(r, c).border = _BORDE
                    if l["estado"] == "pendiente":
                        ws.cell(r, c).fill = PatternFill("solid", fgColor="FFF2CC")
                r += 1
            ultima = r - 1
            ws.cell(r, 5, "Costo unitario").font = Font(bold=True)
            if apu["lineas"]:
                c = ws.cell(r, 6, f"=SUM(F{primera}:F{ultima})")
                c.font, c.number_format = Font(bold=True), _DINERO
            if apu["pendientes"]:
                ws.cell(r, 7, f"Incompleto: faltan {apu['pendientes']} línea(s)").font = Font(italic=True, color="C00000")
            if apu.get("desglose"):  # costos indirectos y precio final según el modelo de cálculo del proyecto
                r += 1
                for d in apu["desglose"]:
                    if d["codigo"].endswith(".directo"):
                        continue
                    ws.cell(r, 2, d["etiqueta"])
                    ws.cell(r, 6, _f(d["valor"])).number_format = _DINERO
                    r += 1
                ws.cell(r, 5, "PRECIO UNITARIO").font = Font(bold=True)
                c = ws.cell(r, 6, _f(apu["precio"]))
                c.font, c.number_format = Font(bold=True), _DINERO
                r += 1
            r += 2
    _anchos(ws, [14, 40, 10, 18, 14, 14, 22, 30])


def _hoja_materiales(wb: Workbook, p: dict) -> None:
    ws = wb.create_sheet("Materiales y recursos")
    ws["A1"] = "LISTA CONSOLIDADA DE RECURSOS (cantidad del ítem × cantidad por unidad)"
    ws["A1"].font = Font(bold=True, size=14)
    grupos: dict[tuple, dict] = {}
    pendientes = 0
    for m in p["modulos"]:
        for it in m["items"]:
            apu, cant_item = it.get("apu"), _f(it.get("cantidad"))
            if not apu or cant_item is None:
                continue
            for l in apu["lineas"]:
                if l["cantidad"] is None:
                    pendientes += 1
                    continue
                nombre = " ".join(preparar(l["descripcion"]).tokens) or l["descripcion"].lower()
                g = grupos.setdefault((l["tipo"], nombre, normalizar_unidad(l["unidad"])), {
                    "tipo": l["tipo"], "nombre": l["descripcion"], "unidad": l["unidad"], "cantidad": Decimal(0),
                    "precios": set(), "items": set()})
                g["cantidad"] += Decimal(it["cantidad"]) * Decimal(l["cantidad"])
                g["items"].add(it["id"])
                if l["precio_unitario"] is not None:
                    g["precios"].add(Decimal(l["precio_unitario"]))
    _cabecera(ws, 3, ["Tipo", "Recurso", "Unidad", "Cantidad total", "Precio (Bs)", "Costo (Bs)", "Usado en"])
    r = 4
    for g in sorted(grupos.values(), key=lambda g: (_ORDEN_TIPO.get(g["tipo"], 9), g["nombre"].lower())):
        ws.cell(r, 1, _TIPO.get(g["tipo"], g["tipo"]))
        ws.cell(r, 2, g["nombre"])
        ws.cell(r, 3, g["unidad"])
        ws.cell(r, 4, float(round(g["cantidad"], 4))).number_format = "#,##0.00##"
        if len(g["precios"]) == 1:
            ws.cell(r, 5, float(next(iter(g["precios"])))).number_format = _DINERO
        elif len(g["precios"]) > 1:
            ws.cell(r, 5, "varios")
        ws.cell(r, 6, f'=IF(ISNUMBER(E{r}),ROUND(D{r}*E{r},2),"")').number_format = _DINERO
        ws.cell(r, 7, f"{len(g['items'])} ítem(s)")
        for c in range(1, 8):
            ws.cell(r, c).border = _BORDE
        r += 1
    ws.cell(r + 1, 5, "TOTAL").font = Font(bold=True)
    t = ws.cell(r + 1, 6, f"=SUM(F4:F{max(r - 1, 4)})")
    t.font, t.number_format = Font(bold=True), _DINERO
    if pendientes:
        ws.cell(r + 3, 1, f"No se incluyen {pendientes} línea(s) de APU que aún no tienen cantidad.").font = Font(italic=True, color="C00000")
    _anchos(ws, [14, 42, 10, 16, 14, 16, 12])


def _fecha(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def _hoja_cronograma(wb: Workbook, c: dict) -> None:
    ws = wb.create_sheet("Cronograma")
    ws["A1"] = "CRONOGRAMA DE EJECUCIÓN"
    ws["A1"].font = Font(bold=True, size=14)
    fin = _fecha(c.get("fecha_fin"))
    ws["A2"] = (f"Inicio: {_fecha(c['fecha_inicio']):%d/%m/%Y} · Fin: {fin:%d/%m/%Y} · {c['dias_habiles']} días hábiles"
                if fin else "No hay ítems que se puedan programar todavía.")
    titulos = ["Ítem", "Actividad", "Personas", "Horas-hombre", "Días háb.", "Inicio", "Fin", "Holgura", "Crítica", "Nota"]
    _cabecera(ws, 4, titulos)
    inicio_g = len(titulos) + 1
    lunes0 = None
    n_sem = 0
    if fin:
        ini = _fecha(c["fecha_inicio"])
        lunes0 = ini - timedelta(days=ini.weekday())
        n_sem = min(104, math.ceil(((fin - lunes0).days + 1) / 7))
        for w in range(n_sem):
            cel = ws.cell(4, inicio_g + w, lunes0 + timedelta(days=7 * w))
            cel.number_format = "dd/mm"
            cel.font = Font(bold=True, color="FFFFFF", size=8)
            cel.fill = PatternFill("solid", fgColor=AZUL)
            cel.alignment = Alignment(textRotation=90, horizontal="center")
            ws.column_dimensions[get_column_letter(inicio_g + w)].width = 3.2
    ws.row_dimensions[4].height = 40
    r = 5
    for m in c["modulos"]:
        acts = [a for a in c["actividades"] if a["modulo_id"] == m["id"]]
        if not acts:
            continue
        hito = f" · hito {_fecha(m['hito']):%d/%m/%Y}" if m.get("hito") else ""
        atraso = f" · ATRASO de {m['atraso_dias']} días hábiles" if m.get("atraso_dias") else ""
        _banda(ws, r, f"{m['codigo']} {m['nombre']}{hito}{atraso}", len(titulos))
        r += 1
        for a in acts:
            ini, fi = _fecha(a["inicio"]), _fecha(a["fin"])
            valores = [a["numero"], a["nombre"], a["personas"], float(a["horas_hombre"]), a["duracion_dias"], ini, fi,
                       a["holgura_dias"], "Sí" if a["critica"] else "", a["nota"]]
            for i, v in enumerate(valores, start=1):
                cel = ws.cell(r, i, v)
                cel.border = _BORDE
                if isinstance(v, date):
                    cel.number_format = "dd/mm/yyyy"
            ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
            if lunes0:
                for w in range(n_sem):
                    s, e = lunes0 + timedelta(days=7 * w), lunes0 + timedelta(days=7 * w + 6)
                    if ini <= e and fi >= s:
                        ws.cell(r, inicio_g + w).fill = PatternFill("solid", fgColor="E57373" if a["critica"] else "64B5F6")
            r += 1
    r += 1
    for aviso in c.get("avisos", []):
        ws.cell(r, 1, aviso).font = Font(color="C00000")
        r += 1
    if c.get("sin_programar"):
        r += 1
        ws.cell(r, 1, "Ítems que no se pudieron programar:").font = Font(bold=True)
        r += 1
        for s in c["sin_programar"]:
            ws.cell(r, 1, f"Ítem {s['numero']}: {s['nombre']} — {s['motivo']}")
            r += 1
    _anchos(ws, [7, 52, 9, 13, 10, 12, 12, 9, 8, 40])
    ws.freeze_panes = "C5"


def exportar_xlsx(proyecto: dict, cronograma: Optional[dict] = None, solo: Optional[str] = None) -> bytes:
    """`solo`: None = libro completo; 'b1' = solo el Formulario B-1; 'b2' = solo el análisis de precios (B-2)."""
    if solo not in (None, "b1", "b2"):
        raise ValueError("El formulario debe ser 'b1' o 'b2'.")
    wb = Workbook()
    if solo == "b2":
        wb.remove(wb.active)  # el libro nuevo trae una hoja vacía
        _hoja_apu(wb, proyecto)
    else:
        rangos = _hoja_b1(wb, proyecto)
        if solo is None:
            _hoja_resumen(wb, proyecto, rangos)
            _hoja_apu(wb, proyecto)
            _hoja_materiales(wb, proyecto)
            if cronograma:
                _hoja_cronograma(wb, cronograma)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
