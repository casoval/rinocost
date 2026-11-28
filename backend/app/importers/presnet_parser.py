"""Lector de la «Revista Presupuesto y Construcción» (reporte de PresNet): un análisis de precios unitarios por página.

Convierte cada análisis en un APU de biblioteca con SOLO el costo directo (materiales, mano de obra y equipo con su
cantidad por unidad y su precio). Los costos indirectos de la revista (cargas sociales, IVA, herramientas, gastos generales,
utilidad, IT) NO se guardan: se calculan con el modelo de cálculo que elija cada usuario. Se usan solo para COMPROBAR la
lectura: el precio recalculado con el modelo B-2 debe coincidir con el impreso; si no, se avisa (nunca se corrige).

Nada se corrige en silencio:
- La revista publica la misma unidad («M») en casi todos los ítems; no es confiable, así que la unidad del APU queda VACÍA
  para confirmarla a mano (se avisa).
- Descripciones partidas en varias líneas y análisis repartidos en dos páginas se reconstruyen; el resto lo dudoso es alerta.

Ejecutar desde backend/:
    python -m app.importers presnet ruta/revista.pdf --excel biblioteca_revista.xlsx [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from ..costos import b2_con_porcentajes, calcular
from .biblioteca_excel import COLUMNAS, AlertaFila, ApuImportado, LineaImportada, ResultadoBiblioteca

_NUM = r"\d[\d,]*\.\d+"
_FILA = re.compile(rf"^(\d{{1,3}})\s+(?:(.*?)\s+)?(\S+)\s+({_NUM})\s+({_NUM})\s+({_NUM})$")
_NUM_FIN = re.compile(rf"({_NUM})\s*$")
_SECCIONES = [
    (re.compile(r"^1\.\s*MATERIALES\b"), "material"),
    (re.compile(r"^2\.\s*MANO DE OBRA\b"), "mano_obra"),
    (re.compile(r"^3\.\s*EQUIPO\b"), "equipo"),
    (re.compile(r"^4\.\s*GASTOS\b"), None),
    (re.compile(r"^5\.\s*UTILIDAD\b"), None),
    (re.compile(r"^6\.\s*IMPUESTOS\b"), None),
]
_IGNORAR = re.compile(r"^(TOTAL|SUBTOTAL|\*|CARGAS|IMPUESTOS|GASTOS|UTILIDAD|HERRAMIENTAS|DESCRIPCI[ÓO]N|PRODUCTIVO|P[ÁA]G\.|Son\s*:|ANÁLISIS|AN[ÁA]LISIS)", re.I)
_PORC = {
    "pct_cargas": re.compile(r"CARGAS SOCIALES\s*=\s*\(\s*([\d.]+)\s*%"),
    "pct_iva_mo": re.compile(r"IVA MANO DE OBRA\s*=\s*\(\s*([\d.]+)\s*%"),
    "pct_herr": re.compile(r"HERRAMIENTAS\s*=\s*\(\s*([\d.]+)\s*%"),
    "pct_gg": re.compile(r"GASTOS GENERALES\s*=\s*([\d.]+)\s*%"),
    "pct_util": re.compile(r"UTILIDAD\s*=\s*([\d.]+)\s*%"),
    "pct_it": re.compile(r"IMPUESTOS IT\s*=\s*([\d.]+)\s*%"),
}
_TOL = Decimal("0.02")


def _num(texto: str) -> Decimal:
    return Decimal(texto.replace(",", ""))


@dataclass
class ApuPresnet(ApuImportado):
    pagina: int = 0
    unidad_publicada: str = ""
    precio_impreso: Optional[Decimal] = None
    precio_recalculado: Optional[Decimal] = None


@dataclass
class ResultadoPresnet(ResultadoBiblioteca):
    encabezado: str = ""
    paginas: int = 0

    def resumen(self) -> dict:
        por_tipo = {t: len({l.recurso for a in self.apus for l in a.lineas if l.tipo == t}) for t in ("material", "mano_obra", "equipo")}
        return {
            "paginas": self.paginas, "apus": len(self.apus), "lineas": self.total_lineas, "recursos_distintos": por_tipo,
            "coinciden_con_el_precio_impreso": sum(1 for a in self.apus if a.precio_impreso is not None and a.precio_recalculado == a.precio_impreso),
            "alertas": dict(collections.Counter(a.codigo for a in self.alertas)),
        }


def _filas_de_seccion(lineas: list[str]) -> list[dict]:
    """Une las descripciones partidas: el texto justo antes de una fila SIN descripción es su comienzo; el resto de las
    líneas de texto continúa la fila anterior."""
    items: list[tuple] = []
    for l in lineas:
        m = _FILA.match(l)
        if m:
            items.append(("fila", m))
        elif l and not _IGNORAR.match(l):
            items.append(("texto", l))
    filas: list[dict] = []
    k, n = 0, len(items)
    while k < n:
        if items[k][0] == "fila":
            m = items[k][1]
            filas.append({"desc": (m.group(2) or "").strip(), "unidad": m.group(3), "cant": m.group(4),
                          "precio": m.group(5), "costo": m.group(6), "antes": [], "despues": []})
            k += 1
            continue
        j = k
        while j < n and items[j][0] == "texto":
            j += 1
        textos = [items[x][1] for x in range(k, j)]
        siguiente_vacia = j < n and not (items[j][1].group(2) or "").strip()
        if siguiente_vacia:
            comienzo, resto = textos[-1:], textos[:-1]
            if resto and filas:
                filas[-1]["despues"].extend(resto)
            elif resto:
                comienzo = textos
            m = items[j][1]
            filas.append({"desc": "", "unidad": m.group(3), "cant": m.group(4), "precio": m.group(5), "costo": m.group(6),
                          "antes": comienzo, "despues": []})
            k = j + 1
        else:
            if filas:
                filas[-1]["despues"].extend(textos)
            k = j
    return filas


def _descripcion(f: dict) -> str:
    return re.sub(r"\s+", " ", " ".join([*f["antes"], f["desc"], *f["despues"]])).strip()


def _paginas_a_apus(paginas: list[str]) -> list[tuple[int, list[str]]]:
    """Agrupa las líneas de cada análisis; una página sin «Actividad» continúa el análisis anterior."""
    grupos: list[tuple[int, list[str]]] = []
    for n, texto in enumerate(paginas, 1):
        lineas = [re.sub(r"\s+", " ", l).strip() for l in (texto or "").splitlines()]
        lineas = [l for l in lineas if l]
        if any(re.match(r"^Actividad\s*:", l) for l in lineas) or not grupos:
            grupos.append((n, lineas))
        else:
            grupos[-1][1].extend(lineas)
    return grupos


def leer_paginas(paginas: list[str]) -> ResultadoPresnet:
    res = ResultadoPresnet(paginas=len(paginas), hoja="PresNet")
    unidades = collections.Counter()
    for pagina, lineas in _paginas_a_apus(paginas):
        nombre, partes_nombre, unidad_pub, seccion = "", [], "", None
        por_seccion: dict[str, list[str]] = {"material": [], "mano_obra": [], "equipo": []}
        impreso = tot_mat = sub_mo = None
        porc: dict[str, str] = {}
        leyendo_nombre = False
        previas: list[str] = []   # el nombre puede empezar en la línea de ARRIBA de «Actividad :» (celda centrada)
        tras_modulo = False
        for l in lineas:
            if not res.encabezado and l.upper().startswith("REVISTA "):
                res.encabezado = l.rstrip(" -")
            if re.match(r"^M[óo]dulo\s*:", l):
                previas, tras_modulo = [], True
                continue
            m = re.match(r"^Actividad\s*:\s*(.*)$", l)
            if m:
                partes_nombre, leyendo_nombre, tras_modulo = [*previas, m.group(1).strip()], True, False
                continue
            if tras_modulo:
                previas.append(l)
                continue
            if leyendo_nombre:
                if re.match(r"^(Cantidad|Unidad|Moneda)\s*:", l):
                    leyendo_nombre = False
                else:
                    partes_nombre.append(l)
                    continue
            m = re.match(r"^Unidad\s*:\s*(.*)$", l)
            if m:
                unidad_pub = m.group(1).strip()
                continue
            hallada = False
            for rx, sec in _SECCIONES:
                if rx.match(l):
                    seccion, hallada = sec, True
                    break
            if hallada:
                continue
            for clave, rx in _PORC.items():
                mm = rx.search(l)
                if mm:
                    porc[clave] = mm.group(1)
            if re.match(r"^TOTAL MATERIALES\b", l) and _NUM_FIN.search(l):
                tot_mat = _num(_NUM_FIN.search(l).group(1))
            elif re.match(r"^SUBTOTAL MANO DE OBRA\b", l) and _NUM_FIN.search(l):
                sub_mo = _num(_NUM_FIN.search(l).group(1))
            elif "ADOPTADO" in l and _NUM_FIN.search(l):
                impreso = _num(_NUM_FIN.search(l).group(1))
            elif seccion:
                por_seccion[seccion].append(l)
        nombre = re.sub(r"\s+", " ", " ".join(partes_nombre)).strip()
        if not nombre:
            res.alertas.append(AlertaFila("advertencia", "pagina_sin_actividad", f"Pág. {pagina}: no se encontró el nombre de la actividad.", pagina))
            continue
        apu = ApuPresnet(nombre=nombre, unidad="", codigo=f"REV-{len(res.apus) + 1:03d}", fila=pagina, pagina=pagina,
                         unidad_publicada=unidad_pub, precio_impreso=impreso)
        unidades[unidad_pub] += 1
        dirs = {"material": Decimal(0), "mano_obra": Decimal(0), "equipo": Decimal(0)}
        for tipo, lns in por_seccion.items():
            for f in _filas_de_seccion(lns):
                desc = _descripcion(f)
                cant, precio, costo = _num(f["cant"]), _num(f["precio"]), _num(f["costo"])
                if not desc:
                    res.alertas.append(AlertaFila("advertencia", "recurso_sin_nombre", f"Pág. {pagina} («{nombre}»): una fila de {tipo} no tiene descripción legible.", pagina))
                    desc = "(sin descripción)"
                if abs(cant * precio - costo) > Decimal("0.011"):
                    res.alertas.append(AlertaFila("advertencia", "costo_de_fila_distinto",
                        f"Pág. {pagina} («{nombre}»), «{desc}»: cantidad × precio = {cant * precio:.2f}, la revista imprime {costo}.", pagina))
                apu.lineas.append(LineaImportada(tipo, desc, f["unidad"], cant, precio, "referencial", pagina))
                dirs[tipo] += cant * precio
        if not apu.lineas:
            res.alertas.append(AlertaFila("advertencia", "apu_sin_lineas", f"Pág. {pagina}: «{nombre}» no tiene recursos leídos.", pagina))
        # --- comprobaciones contra lo impreso (solo avisan)
        if tot_mat is not None and abs(dirs["material"] - tot_mat) > _TOL:
            res.alertas.append(AlertaFila("advertencia", "total_materiales_distinto",
                f"Pág. {pagina} («{nombre}»): las filas de materiales suman {dirs['material']:.2f} pero la revista imprime {tot_mat}. Revisa el análisis.", pagina))
        if sub_mo is not None and abs(dirs["mano_obra"] - sub_mo) > _TOL:
            res.alertas.append(AlertaFila("advertencia", "subtotal_mano_obra_distinto",
                f"Pág. {pagina} («{nombre}»): las filas de mano de obra suman {dirs['mano_obra']:.2f} pero la revista imprime {sub_mo}.", pagina))
        try:
            modelo = b2_con_porcentajes(**{k: v for k, v in porc.items() if len(porc) == len(_PORC)})
        except Exception:  # noqa: BLE001
            modelo = b2_con_porcentajes()
        if len(porc) != len(_PORC):
            res.alertas.append(AlertaFila("info", "porcentajes_no_leidos", f"Pág. {pagina} («{nombre}»): no se leyeron todos los porcentajes; se comprueba con los B-2 estándar.", pagina))
        apu.precio_recalculado = calcular(modelo, dirs["material"], dirs["mano_obra"], dirs["equipo"]).precio
        if impreso is not None and apu.precio_recalculado != impreso:
            res.alertas.append(AlertaFila("advertencia", "precio_distinto",
                f"Pág. {pagina} («{nombre}»): recalculado con el B-2 = {apu.precio_recalculado}, impreso = {impreso}.", pagina))
        if impreso is None:
            res.alertas.append(AlertaFila("advertencia", "sin_precio_impreso", f"Pág. {pagina} («{nombre}»): no se encontró el precio unitario impreso; no se pudo comprobar.", pagina))
        res.apus.append(apu)

    # --- unidad: si casi todos dicen lo mismo, no es información
    if res.apus and unidades:
        comun, veces = unidades.most_common(1)[0]
        if comun and veces / len(res.apus) >= 0.9:
            res.alertas.append(AlertaFila("info", "unidad_no_publicada",
                f"La revista publica la unidad «{comun}» en {veces} de {len(res.apus)} análisis: no es confiable. La unidad de los APU queda "
                f"VACÍA para confirmarla a mano.", None))
        else:
            for a in res.apus:
                a.unidad = a.unidad_publicada
    nombres = collections.Counter(a.nombre for a in res.apus)
    for nom, v in nombres.items():
        if v > 1:
            res.alertas.append(AlertaFila("advertencia", "apu_repetido", f"El nombre «{nom}» aparece en {v} análisis; se importan todos (código distinto).", None))
    return res


def leer_presnet(fuente: Union[str, Path], progreso: Optional[Callable[[int, int], None]] = None) -> ResultadoPresnet:
    import pdfplumber

    textos: list[str] = []
    with pdfplumber.open(str(fuente)) as pdf:
        total = len(pdf.pages)
        for i, pagina in enumerate(pdf.pages, 1):
            textos.append(pagina.extract_text() or "")
            if progreso:
                progreso(i, total)
    return leer_paginas(textos)


def escribir_excel(res: ResultadoBiblioteca, ruta: Union[str, Path]) -> None:
    """Escribe la biblioteca en el formato que ya importa la app («Importar biblioteca (Excel)»): una fila por recurso."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    tipos = {"material": "Material", "mano_obra": "Mano de obra", "equipo": "Equipo"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Biblioteca"
    ws.append(COLUMNAS)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1D4F91")
    amarillo = PatternFill("solid", fgColor="FFF2CC")
    for a in res.apus:
        primera = True
        for l in a.lineas:
            ws.append([a.nombre if primera else None, a.unidad or None if primera else None, tipos[l.tipo], l.recurso, l.unidad,
                       float(l.cantidad) if l.cantidad is not None else None, float(l.precio_unitario) if l.precio_unitario is not None else None,
                       l.origen_rendimiento, a.codigo if primera else None])
            if primera and not a.unidad:
                ws.cell(ws.max_row, 2).fill = amarillo  # unidad por confirmar
            primera = False
    for i, ancho in enumerate([50, 14, 16, 44, 10, 12, 16, 22, 12], start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "A2"
    inf = wb.create_sheet("Informe")
    inf.append(["Nivel", "Código", "Mensaje", "Pág."])
    for c in inf[1]:
        c.font = Font(bold=True)
    for al in res.alertas:
        inf.append([al.nivel, al.codigo, al.mensaje, al.fila])
    for i, ancho in enumerate([14, 30, 140, 8], start=1):
        inf.column_dimensions[get_column_letter(i)].width = ancho
    ayuda = wb.create_sheet("Instrucciones")
    for linea in ["Escribe la unidad de cada ítem en la columna «Unidad del APU» (celdas amarillas) y guarda el archivo.",
                  "Después, en la app: Bibliotecas → Importar biblioteca (Excel).",
                  "Cantidad = consumo o rendimiento POR UNIDAD DEL ÍTEM. Los precios están en bolivianos y son los de la fuente.",
                  "Los costos indirectos (cargas sociales, impuestos, gastos generales, utilidad) NO están aquí: los calcula el modelo de cálculo.",
                  "La hoja «Informe» lista lo que la lectura comprobó y lo dudoso."]:
        ayuda.append([linea])
    ayuda.column_dimensions["A"].width = 120
    wb.save(str(ruta))


def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Lee la revista PresNet (PDF) y genera la biblioteca en Excel.")
    ap.add_argument("pdf")
    ap.add_argument("--excel", help="ruta del Excel a generar")
    ap.add_argument("--json", action="store_true", help="imprime el resumen como JSON")
    a = ap.parse_args(argv)
    res = leer_presnet(a.pdf, lambda i, n: print(f"\rLeyendo página {i}/{n}", end="", file=sys.stderr) if i % 25 == 0 or i == n else None)
    print(file=sys.stderr)
    if a.excel:
        escribir_excel(res, a.excel)
    resumen = res.resumen()
    if a.json:
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
    else:
        print(f"Páginas: {resumen['paginas']} · APU: {resumen['apus']} · líneas: {resumen['lineas']}")
        print(f"Recursos distintos: {resumen['recursos_distintos']}")
        print(f"Coinciden con el precio impreso: {resumen['coinciden_con_el_precio_impreso']} de {resumen['apus']}")
        for cod, n in resumen["alertas"].items():
            print(f"  alerta {cod}: {n}")
        for al in res.alertas:
            if al.nivel == "advertencia":
                print("  -", al.mensaje)
        if a.excel:
            print(f"Excel escrito en {a.excel}")
    return 0
