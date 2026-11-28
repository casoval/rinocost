"""PDF listo para imprimir de los formularios B-1 y B-2, con el formato del DBC (Documento Base de Contratación).

- Formulario B-1: Presupuesto por ítems y general de la obra (ítem, descripción, unidad, cantidad, precio unitario en
  numeral y literal, precio total, y precio total de la obra en numeral y literal).
- Formulario B-2: Análisis de precios unitarios, UNO POR ÍTEM (una hoja por ítem), con las secciones del modelo de
  cálculo del proyecto (materiales, mano de obra, equipo, gastos generales, utilidad, impuestos...).

Igual que el Excel, recibe diccionarios (la salida JSON del proyecto), no objetos de base de datos. Nunca inventa
datos: lo que falta se imprime como «—» y se avisa al pie.
"""
from __future__ import annotations

import io
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..costos import ModeloCostos, calcular, obtener_predefinido
from .letras import numero_a_letras

# Colores tomados del DBC: encabezado de tabla celeste, bandas de sección azul oscuro.
AZUL_OSCURO = colors.HexColor("#1F3864")
CELESTE = colors.HexColor("#DCE6F1")
CELESTE_SUAVE = colors.HexColor("#EEF3F9")
GRIS_LINEA = colors.HexColor("#7F7F7F")
GRIS_MODULO = colors.HexColor("#F0F0F0")
ROJO = colors.HexColor("#B3261E")

MARGEN = 36  # 0,5 pulgada
ANCHO = letter[0] - 2 * MARGEN  # 540 pt

# ---- Fuentes -----------------------------------------------------------------------------------------------
# Se prefiere una fuente Unicode (Arial en Windows, Liberation/DejaVu en Linux). Si no hay ninguna se usa Helvetica,
# que cubre el español pero no símbolos raros: en ese caso se reemplazan por «?» en vez de dibujar cuadros.
_CANDIDATAS = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf"),
]
_FUENTES: Optional[tuple[str, str, str, bool]] = None


def _fuentes() -> tuple[str, str, str, bool]:
    """(normal, negrita, cursiva, es_unicode)."""
    global _FUENTES
    if _FUENTES is not None:
        return _FUENTES
    for normal, negrita, cursiva in _CANDIDATAS:
        if all(os.path.exists(r) for r in (normal, negrita, cursiva)):
            try:
                pdfmetrics.registerFont(TTFont("RC-Normal", normal))
                pdfmetrics.registerFont(TTFont("RC-Negrita", negrita))
                pdfmetrics.registerFont(TTFont("RC-Cursiva", cursiva))
                _FUENTES = ("RC-Normal", "RC-Negrita", "RC-Cursiva", True)
                return _FUENTES
            except Exception:  # fuente dañada: se prueba la siguiente
                continue
    _FUENTES = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", False)
    return _FUENTES


def _limpio(texto: object) -> str:
    """Texto seguro para la fuente en uso (con Helvetica, lo que no es Latin-1/cp1252 se reemplaza)."""
    s = "" if texto is None else str(texto)
    if _fuentes()[3]:
        return s
    return s.encode("cp1252", errors="replace").decode("cp1252")


def _esc(texto: object) -> str:
    return _limpio(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _estilos() -> dict[str, ParagraphStyle]:
    n, b, i, _ = _fuentes()
    base = ParagraphStyle("base", fontName=n, fontSize=8, leading=9.6)
    return {
        "celda": base,
        "celda_c": ParagraphStyle("celda_c", parent=base, alignment=TA_CENTER),
        "celda_d": ParagraphStyle("celda_d", parent=base, alignment=TA_RIGHT),
        "cab": ParagraphStyle("cab", parent=base, fontName=b, alignment=TA_CENTER),
        "negrita": ParagraphStyle("negrita", parent=base, fontName=b),
        "negrita_d": ParagraphStyle("negrita_d", parent=base, fontName=b, alignment=TA_RIGHT),
        "banda": ParagraphStyle("banda", parent=base, fontName=b, textColor=colors.white, fontSize=8.5),
        "modulo": ParagraphStyle("modulo", parent=base, fontName=b),
        "titulo": ParagraphStyle("titulo", parent=base, fontName=b, fontSize=11, leading=14, alignment=TA_CENTER),
        "nota": ParagraphStyle("nota", parent=base, fontName=i, fontSize=7.5, leading=9, alignment=TA_LEFT),
        "aviso": ParagraphStyle("aviso", parent=base, textColor=ROJO, fontSize=8),
    }


# ---- Formato de números (Bolivia: punto de miles, coma decimal) ----------------------------------------------

def _num(valor: Optional[str | Decimal], dec: int = 2) -> str:
    if valor is None or valor == "":
        return "—"
    d = Decimal(str(valor)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    entero, _, frac = f"{abs(d):.{dec}f}".partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    texto = entero + ("," + frac if dec else "")
    return ("-" if d < 0 else "") + texto


def _cant(valor: Optional[str], texto_original: str = "") -> str:
    """Cantidad de un ítem: hasta 4 decimales sin ceros sobrantes (mínimo 2)."""
    if valor is None:
        return texto_original or "—"
    d = Decimal(valor)
    dec = 2
    for k in (2, 3, 4):
        if d == d.quantize(Decimal(1).scaleb(-k)):
            dec = k
            break
        dec = 4
    return _num(d, dec)


# ---- Página -------------------------------------------------------------------------------------------------

def _pie(titulo_corto: str):
    n = _fuentes()[0]

    def dibujar(canvas, doc):
        canvas.saveState()
        canvas.setFont(n, 7.5)
        canvas.setFillColor(GRIS_LINEA)
        canvas.drawString(MARGEN, letter[1] - 24, _limpio(titulo_corto))
        canvas.setStrokeColor(GRIS_LINEA)
        canvas.setLineWidth(0.6)
        canvas.line(MARGEN, letter[1] - 28, letter[0] - MARGEN, letter[1] - 28)
        canvas.drawRightString(letter[0] - MARGEN, 22, f"Página {doc.page}")
        canvas.restoreState()

    return dibujar


def _documento(buf: io.BytesIO, titulo: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=44, bottomMargin=40,
        title=_limpio(titulo), author="RinoCost",
    )


def _p(texto: object, estilo: ParagraphStyle) -> Paragraph:
    return Paragraph(_esc(texto), estilo)


# ---- Formulario B-1 -----------------------------------------------------------------------------------------

NOTA_B1 = ("NOTA.- La empresa proponente declara de forma expresa que el presente Formulario contiene los mismos "
           "precios unitarios que los señalados en el Formulario B-2.")


def exportar_b1_pdf(proyecto: dict) -> bytes:
    """Formulario B-1 del proyecto, en el formato del DBC."""
    est = _estilos()
    buf = io.BytesIO()
    doc = _documento(buf, f"Formulario B-1 – {proyecto['nombre']}")
    historia: list = [
        _p("FORMULARIO B-1", est["titulo"]),
        _p("PRESUPUESTO POR ÍTEMS Y GENERAL DE LA OBRA", est["titulo"]),
        _p("(En bolivianos)", est["titulo"]),
        Spacer(1, 4),
        Paragraph(f"<b>Proyecto:</b> {_esc(proyecto['nombre'])}", est["celda"]),
        Spacer(1, 6),
    ]
    anchos = [30, 182, 38, 48, 56, 118, 68]
    filas: list[list] = [[
        _p("Ítem", est["cab"]), _p("Descripción", est["cab"]), _p("Unidad", est["cab"]), _p("Cantidad", est["cab"]),
        _p("Precio Unitario (Numeral)", est["cab"]), _p("Precio Unitario (Literal)", est["cab"]),
        _p("Precio Total (Numeral)", est["cab"]),
    ]]
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.5, GRIS_LINEA), ("BACKGROUND", (0, 0), (-1, 0), CELESTE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    sin_precio = 0
    for m in proyecto["modulos"]:
        if not m["items"]:
            continue
        filas.append([_p(f"{m['codigo']}  {m['nombre']}", est["modulo"])] + [""] * 6)
        r = len(filas) - 1
        estilo += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), GRIS_MODULO)]
        for it in m["items"]:
            pu = it.get("precio_unitario")
            if pu is None:
                sin_precio += 1
            filas.append([
                _p(it["numero"], est["celda_c"]), _p(it["descripcion"], est["celda"]), _p(it["unidad"], est["celda_c"]),
                _p(_cant(it.get("cantidad"), it.get("cantidad_texto", "")), est["celda_d"]),
                _p(_num(pu), est["celda_d"]),
                _p(numero_a_letras(Decimal(pu)) if pu is not None else "—", est["celda"]),
                _p(_num(it.get("total")), est["celda_d"]),
            ])
    total = proyecto.get("total")
    filas.append([_p("PRECIO TOTAL (Numeral)", est["negrita_d"])] + [""] * 5 + [_p(_num(total), est["negrita_d"])])
    r = len(filas) - 1
    estilo += [("SPAN", (0, r), (5, r)), ("BACKGROUND", (0, r), (5, r), CELESTE)]
    filas.append([_p("PRECIO TOTAL (Literal)", est["negrita_d"])] + [""] * 4
                 + [_p(numero_a_letras(Decimal(total)) if total is not None else "—", est["celda"]), ""])
    r = len(filas) - 1  # el literal ocupa las dos últimas columnas para que no quede apretado
    estilo += [("SPAN", (0, r), (4, r)), ("SPAN", (5, r), (6, r)), ("BACKGROUND", (0, r), (4, r), CELESTE)]
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    historia.append(tabla)
    historia += [Spacer(1, 6), _p(NOTA_B1, est["nota"])]
    if sin_precio:
        historia += [Spacer(1, 4), _p(
            f"Atención: {sin_precio} ítem(s) todavía no tienen precio unitario; el precio total es parcial. "
            "Complete los análisis de precios antes de presentar este formulario.", est["aviso"])]
    doc.build(historia, onFirstPage=_pie(f"Formulario B-1 · {proyecto['nombre']}"),
              onLaterPages=_pie(f"Formulario B-1 · {proyecto['nombre']}"))
    return buf.getvalue()


# ---- Formulario B-2 -----------------------------------------------------------------------------------------

NOTA_B2 = ("NOTA.- El Proponente declara que el presente Formulario ha sido llenado de acuerdo con las "
           "especificaciones técnicas, aplicando las leyes sociales y tributarias vigentes, y es consistente con el "
           "Formulario B-3.")
_ANCHOS_B2 = [22, 238, 55, 70, 80, 75]  # N°, descripción, unidad, cantidad, precio productivo, costo total


def _costo_linea(l: dict) -> Optional[Decimal]:
    if l.get("cantidad") is None or l.get("precio_unitario") is None:
        return None
    return (Decimal(l["cantidad"]) * Decimal(l["precio_unitario"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _bloque_b2(p: dict, it: dict, modelo: dict, est: dict) -> list:
    """Una hoja del B-2: el análisis de precios de un ítem."""
    apu = it["apu"]
    resultado = _calcular_exacto(modelo, apu)  # None si el análisis está incompleto: nunca se inventa un precio
    desglose = {l.codigo: l.valor for l in resultado.lineas} if resultado else {}
    decimales = int(modelo.get("decimales", 2))
    out: list = [_p("FORMULARIO B-2", est["titulo"]), _p("ANÁLISIS DE PRECIOS UNITARIOS", est["titulo"]), Spacer(1, 6)]

    # DATOS GENERALES
    datos = Table(
        [[_p("DATOS GENERALES", est["banda"]), ""]]
        + [[_p(k + " :", est["negrita_d"]), _p(v, est["celda"])] for k, v in (
            ("Proyecto", p["nombre"]), ("Actividad", f"{it['numero']}. {it['descripcion']}"),
            ("Cantidad", _cant(it.get("cantidad"), it.get("cantidad_texto", ""))), ("Unidad", it["unidad"]),
            ("Moneda", "Bolivianos"))],
        colWidths=[110, ANCHO - 110])
    datos.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)), ("BACKGROUND", (0, 0), (1, 0), AZUL_OSCURO),
        ("BACKGROUND", (1, 1), (1, -1), CELESTE_SUAVE), ("BOX", (1, 1), (1, -1), 0.5, GRIS_LINEA),
        ("INNERGRID", (1, 1), (1, -1), 0.5, GRIS_LINEA), ("BOX", (0, 0), (-1, -1), 0.8, AZUL_OSCURO),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    out += [datos, Spacer(1, 2)]

    secciones = [s for s in modelo["secciones"] if s.get("activo", True)]
    hay_pendientes = False
    for n, s in enumerate(secciones, start=1):
        tipo = s.get("tipo_recurso")
        lineas = [l for l in apu["lineas"] if tipo and l["tipo"] == tipo]
        pasos = [q for q in s.get("pasos", []) if q.get("activo", True)]
        filas: list[list] = [[_p(f"{n}.   {s['titulo']}", est["banda"])] + [""] * 5]
        estilo = [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), AZUL_OSCURO), ("BOX", (0, 0), (-1, -1), 0.8, AZUL_OSCURO)]
        if tipo:
            filas.append([_p("DESCRIPCIÓN", est["cab"]), "", _p("UNIDAD", est["cab"]), _p("CANTIDAD", est["cab"]),
                          _p("PRECIO PRODUCTIVO", est["cab"]), _p("COSTO TOTAL", est["cab"])])
            estilo += [("SPAN", (0, 1), (1, 1))]
        else:
            filas.append([""] * 5 + [_p("COSTO TOTAL", est["cab"])])
            estilo += [("SPAN", (0, 1), (4, 1))]
        estilo += [("BACKGROUND", (0, 1), (-1, 1), CELESTE)]
        if tipo:
            for k, l in enumerate(lineas, start=1):
                pend = l.get("cantidad") is None or l.get("precio_unitario") is None
                hay_pendientes = hay_pendientes or pend
                filas.append([
                    _p(k, est["celda_c"]), _p(l["descripcion"], est["celda"]), _p(l["unidad"], est["celda_c"]),
                    _p(_num(l.get("cantidad"), 4) if l.get("cantidad") is not None else "—", est["celda_d"]),
                    _p(_num(l.get("precio_unitario")), est["celda_d"]), _p(_num(_costo_linea(l)), est["celda_d"]),
                ])
            if not lineas:
                filas.append([_p("—", est["celda_c"]), _p("(sin recursos de este tipo)", est["celda"]), "", "", "", ""])
        directo = desglose.get(f"{s['codigo']}.directo")
        if pasos:
            if tipo == "mano_obra":  # como en el DBC, solo la mano de obra muestra subtotal antes de cargas e IVA
                filas.append([_p(f"SUBTOTAL {s['titulo']}", est["negrita_d"])] + [""] * 4 + [_p(_num(directo), est["negrita_d"])])
                r = len(filas) - 1
                estilo += [("SPAN", (0, r), (4, r))]
            for q in pasos:
                etiqueta = q["etiqueta"].replace("{pct}", _pct(q["porcentaje"]))
                filas.append([_p("*", est["celda_c"]), _p(etiqueta, est["celda_c"]), "", "", "", _p(_num(desglose.get(q["codigo"])), est["celda_d"])])
                r = len(filas) - 1
                estilo += [("SPAN", (1, r), (4, r))]
        total_seccion = resultado.secciones.get(s["codigo"]) if resultado else None
        filas.append([_p(s.get("etiqueta_total") or f"TOTAL {s['titulo']}", est["negrita_d"])] + [""] * 4 + [_p(_num(total_seccion), est["negrita_d"])])
        r = len(filas) - 1
        estilo += [("SPAN", (0, r), (4, r)), ("BACKGROUND", (0, r), (-1, r), CELESTE)]
        tabla = Table(filas, colWidths=_ANCHOS_B2, repeatRows=0)
        tabla.setStyle(TableStyle(estilo + [
            ("INNERGRID", (0, 1), (-1, -1), 0.4, GRIS_LINEA), ("BOX", (0, 1), (-1, -1), 0.5, GRIS_LINEA),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        out += [Spacer(1, 3), tabla]

    suma = " + ".join(str(i) for i in range(1, len(secciones) + 1))
    precio = resultado.precio if resultado else None
    total_sin_redondeo = resultado.total if resultado else None
    cierre = Table([
        [_p(f"TOTAL PRECIO UNITARIO ({suma})", est["negrita_d"]), _p(_num(total_sin_redondeo, decimales + 2), est["negrita_d"])],
        [_p(f"TOTAL PRECIO UNITARIO ADOPTADO (Con {_palabra_decimales(decimales)} decimales)", est["negrita_d"]), _p(_num(precio, decimales), est["negrita_d"])],
    ], colWidths=[ANCHO - 75, 75])
    cierre.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, AZUL_OSCURO), ("INNERGRID", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
        ("BACKGROUND", (0, 0), (-1, -1), CELESTE), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    out += [Spacer(1, 3), cierre, Spacer(1, 4),
            _p("(*) El proponente deberá señalar los porcentajes pertinentes a cada rubro", est["nota"]), _p(NOTA_B2, est["nota"])]
    if hay_pendientes or precio is None:
        out += [Spacer(1, 4), _p("Atención: este análisis tiene líneas sin cantidad o sin precio (—); el precio unitario "
                                  "no se puede calcular hasta completarlas.", est["aviso"])]
    return out


def _calcular_exacto(modelo: dict, apu: dict):
    """Precio del análisis con el mismo motor que usa la app (Decimal, sin redondeos intermedios)."""
    lineas = apu.get("lineas") or []
    if not lineas or any(l.get("cantidad") is None or l.get("precio_unitario") is None for l in lineas):
        return None
    directos = {"material": Decimal(0), "mano_obra": Decimal(0), "equipo": Decimal(0)}
    for l in lineas:
        directos[l["tipo"]] = directos.get(l["tipo"], Decimal(0)) + Decimal(l["cantidad"]) * Decimal(l["precio_unitario"])
    return calcular(ModeloCostos.desde_dict(modelo), directos["material"], directos["mano_obra"], directos["equipo"])


def _pct(texto: Optional[str]) -> str:
    if texto is None:
        return ""
    return _num(texto, 2)


def _palabra_decimales(n: int) -> str:
    return {0: "cero (0)", 1: "un (1)", 2: "dos (2)", 3: "tres (3)", 4: "cuatro (4)"}.get(n, f"({n})")


def exportar_b2_pdf(proyecto: dict) -> bytes:
    """Formulario B-2 de cada ítem que tiene análisis de precios (una hoja por ítem), en el formato del DBC."""
    est = _estilos()
    modelo = proyecto.get("modelo_costos") or obtener_predefinido("costo_directo").a_dict()
    buf = io.BytesIO()
    doc = _documento(buf, f"Formulario B-2 – {proyecto['nombre']}")
    historia: list = []
    omitidos: list[str] = []
    for m in proyecto["modulos"]:
        for it in m["items"]:
            if not it.get("apu") or not it["apu"].get("lineas"):
                omitidos.append(f"{it['numero']}. {it['descripcion']}")
                continue
            if historia:
                historia.append(PageBreak())
            historia += _bloque_b2(proyecto, it, modelo, est)
    if not historia:
        historia = [_p("FORMULARIO B-2", est["titulo"]), _p("ANÁLISIS DE PRECIOS UNITARIOS", est["titulo"]), Spacer(1, 12),
                    _p("Todavía no hay ítems con análisis de precios. Vincula un APU o agrega recursos a los ítems y vuelve a descargar.", est["celda"])]
    if omitidos:
        historia += [PageBreak(), _p("ÍTEMS SIN ANÁLISIS DE PRECIOS", est["titulo"]), Spacer(1, 6),
                     _p(f"Estos {len(omitidos)} ítem(s) no tienen recursos y no se incluyeron en este documento:", est["celda"]), Spacer(1, 4)]
        historia += [_p(t, est["celda"]) for t in omitidos]
    doc.build(historia, onFirstPage=_pie(f"Formulario B-2 · {proyecto['nombre']}"),
              onLaterPages=_pie(f"Formulario B-2 · {proyecto['nombre']}"))
    return buf.getvalue()


def exportar_b2_item_pdf(proyecto: dict, item: dict) -> bytes:
    """Hoja B-2 de un solo ítem (la misma que ve el usuario en la ventana), en el formato del DBC."""
    est = _estilos()
    modelo = proyecto.get("modelo_costos") or obtener_predefinido("costo_directo").a_dict()
    buf = io.BytesIO()
    doc = _documento(buf, f"Formulario B-2 – ítem {item['numero']} – {proyecto['nombre']}")
    if item.get("apu") and item["apu"].get("lineas"):
        historia = _bloque_b2(proyecto, item, modelo, est)
    else:
        historia = [_p("FORMULARIO B-2", est["titulo"]), _p("ANÁLISIS DE PRECIOS UNITARIOS", est["titulo"]), Spacer(1, 12),
                    _p(f"El ítem {item['numero']}. {item['descripcion']} todavía no tiene recursos. "
                       "Vincula un APU o agrega recursos y vuelve a abrir la hoja.", est["celda"])]
    pie = _pie(f"Formulario B-2 · {proyecto['nombre']} · ítem {item['numero']}")
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
