"""PDF del cronograma con el aspecto de MS Project: tabla de tareas a la izquierda y diagrama de Gantt a la derecha.

- Hoja horizontal; el título, el plazo y la ruta crítica van arriba; las columnas se repiten en cada página.
- Tareas azules; ruta crítica (holgura cero) en rojo; resumen de módulo en gris oscuro; hito «Fin de obra» en rombo rojo.
- Flechas de dependencia fin-inicio (solo las que «empujan» el inicio de cada tarea, igual que la ruta crítica).
- Escala por semanas con número de día; si la obra es larga (más de ~8 semanas), meses arriba y semanas abajo.
- Los días no laborables (domingos, sábados si no se trabajan, feriados) se sombrean.
- Duración en días hábiles; Comienzo y Fin son el N° de día calendario desde el inicio de obra (día 1).

Recibe diccionarios (la salida JSON del cronograma), no objetos de base de datos.
"""
from __future__ import annotations

import io
import math
from datetime import date, timedelta
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from .pdf import _fuentes, _limpio

AZUL_TITULO = colors.HexColor("#1F3864")
ROJO = colors.HexColor("#C00000")
ROJO_RELLENO = colors.HexColor("#F4B6B6")
AZUL_BARRA = colors.HexColor("#2E75B6")
AZUL_RELLENO = colors.HexColor("#BDD7EE")
AZUL_BORDE = colors.HexColor("#5B87BF")
CAB_FONDO = colors.HexColor("#DCE6F2")
BANDA = colors.HexColor("#F2F6FB")
GRIS_TEXTO = colors.HexColor("#595959")
GRIS_RESUMEN = colors.HexColor("#595959")
GRIS_DEP = colors.HexColor("#8C8C8C")
GRIS_GRILLA = colors.HexColor("#E3E8EF")
GRIS_NOLAB = colors.HexColor("#EEF0F3")

PAG = landscape(letter)  # 792 × 612
M = 28
ANCHO = PAG[0] - 2 * M
ALTO_FILA = 12.6
ALTO_CAB = 26
COLS = [("Id", 22), ("Nombre de tarea", 205), ("Duración", 41), ("Comienzo", 42), ("Fin", 36), ("Predecesoras", 54)]
ANCHO_TABLA = sum(w for _, w in COLS)
ANCHO_GANTT = ANCHO - ANCHO_TABLA
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
ALTO_PIE = 46
ALTO_TITULO_P1 = 96
ALTO_TITULO_PN = 34


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _a_fecha(v) -> Optional[date]:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _dias(n: int) -> str:
    return f"{n} {'día' if n == 1 else 'días'}"


def _recortar(texto: str, fuente: str, tam: float, ancho: float) -> str:
    texto = _limpio(texto)
    if stringWidth(texto, fuente, tam) <= ancho:
        return texto
    while texto and stringWidth(texto + "…", fuente, tam) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "…"


class _Fila:
    __slots__ = ("id", "tipo", "nombre", "dur", "ini", "fin", "preds", "critica", "item_id", "sangria", "etiqueta")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _armar_filas(crono: dict) -> tuple[list[_Fila], int]:
    """(filas con su Id y predecesoras ya traducidas a Id, total de días calendario)."""
    inicio = _a_fecha(crono["fecha_inicio"])
    dia = lambda d: (_a_fecha(d) - inicio).days + 1  # noqa: E731
    filas: list[_Fila] = []
    fila_de_item: dict[int, _Fila] = {}
    siguiente = 1
    for m in crono["modulos"]:
        acts = [a for a in crono["actividades"] if a["modulo_id"] == m["id"]]
        if not acts:
            continue
        filas.append(_Fila(id=siguiente, tipo="modulo", nombre=f"{m['codigo']} - {m['nombre']}".strip(" -"),
                           dur=m.get("dias_habiles") or max(a["duracion_dias"] for a in acts),
                           ini=dia(m["inicio"]), fin=dia(m["fin"]), preds=[], critica=False, item_id=None, sangria=0))
        siguiente += 1
        for a in acts:
            f = _Fila(id=siguiente, tipo="tarea", nombre=f"{a['numero']}. {a['nombre']}", dur=a["duracion_dias"],
                      ini=dia(a["inicio"]), fin=dia(a["fin"]), preds=list(a.get("predecesoras") or []),
                      critica=bool(a["critica"]), item_id=a["item_id"], sangria=1,
                      etiqueta=f"F{a['frente']}" if (crono.get("frentes") or 0) > 1 and a.get("frente") else "")
            fila_de_item[a["item_id"]] = f
            filas.append(f)
            siguiente += 1
    total = (_a_fecha(crono["fecha_fin"]) - inicio).days + 1 if crono.get("fecha_fin") else 1
    ultimas = [f for f in fila_de_item.values() if f.fin == total]
    filas.append(_Fila(id=siguiente, tipo="hito", nombre="FIN DE OBRA", dur=0, ini=total, fin=total,
                       preds=[f.item_id for f in ultimas], critica=True, item_id=None, sangria=0))
    for f in filas:  # ids de ítem -> Id de fila
        f.preds = [fila_de_item[i].id for i in f.preds if i in fila_de_item]
    return filas, total


def _no_laborables(inicio: date, total: int, sabados: bool, feriados: set[date]) -> set[int]:
    limite = 6 if sabados else 5
    out = set()
    for i in range(total):
        d = inicio + timedelta(days=i)
        if d.weekday() >= limite or d in feriados:
            out.add(i + 1)
    return out


def _ruta_critica(crono: dict, flecha: str, ancho: float, fuente: str, tam: float) -> str:
    crit = sorted((a for a in crono["actividades"] if a["critica"]), key=lambda a: (a["inicio"], a["numero"]))
    if not crit:
        return ""
    nombres = []
    for a in crit:
        n = a["nombre"].split("(")[0].strip().lower()
        nombres.append(n if len(n) <= 26 else n[:25].rstrip() + "…")
    for k in range(len(nombres), 0, -1):
        texto = "Ruta crítica: " + f" {flecha} ".join(nombres[:k]) + (f" {flecha} …" if k < len(nombres) else "")
        if stringWidth(_limpio(texto), fuente, tam) <= ancho:
            return texto
    return _recortar("Ruta crítica: " + nombres[0], fuente, tam, ancho)


def exportar_cronograma_pdf(
    proyecto: dict, crono: dict, empresa: Optional[str] = None, trabaja_sabados: bool = False,
    feriados: Optional[list] = None, tipo_plazo: Optional[str] = None,
) -> bytes:
    normal, negrita, cursiva, unicode_ok = _fuentes()
    flecha = "→" if unicode_ok else ">"
    inicio = _a_fecha(crono["fecha_inicio"])
    filas, total = _armar_filas(crono)
    tipo = tipo_plazo or crono.get("tipo_plazo") or "calendario"
    plazo_txt = (f"{crono['dias_habiles']} DÍAS HÁBILES" if tipo == "habiles" else f"{total} DÍAS CALENDARIO")
    if not crono.get("actividades"):
        plazo_txt = "SIN ACTIVIDADES PROGRAMABLES"
    nolab = _no_laborables(inicio, total, trabaja_sabados, {_a_fecha(f) for f in (feriados or [])})
    dpx = ANCHO_GANTT / max(total, 1)
    modo_dias = dpx >= 6.0

    # ---- paginación ----
    paginas: list[list[_Fila]] = []
    actual: list[_Fila] = []
    disp = PAG[1] - 2 * M - ALTO_PIE - ALTO_TITULO_P1 - ALTO_CAB
    for f in filas:
        if (len(actual) + 1) * ALTO_FILA > disp:
            paginas.append(actual)
            actual, disp = [], PAG[1] - 2 * M - ALTO_PIE - ALTO_TITULO_PN - ALTO_CAB
        actual.append(f)
    paginas.append(actual)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAG)
    c.setTitle(_limpio(f"Cronograma - {proyecto.get('nombre', '')}"))
    c.setAuthor("RinoCost")
    gx = M + ANCHO_TABLA  # origen del Gantt

    def x_dia(d: float) -> float:  # borde izquierdo del día d (1 = primer día)
        return gx + (d - 1) * dpx

    for n_pag, pag in enumerate(paginas, 1):
        y = PAG[1] - M
        # ---- título ----
        if n_pag == 1:
            c.setFillColor(AZUL_TITULO); c.setFont(negrita, 19)
            c.drawCentredString(PAG[0] / 2, y - 18, "CRONOGRAMA DE ACTIVIDADES")
            c.setFillColor(ROJO); c.setFont(negrita, 12.5)
            c.drawCentredString(PAG[0] / 2, y - 36, _limpio(f"PLAZO DE EJECUCIÓN: {plazo_txt}"))
            extra = ""
            if crono.get("plazo_maximo"):
                u = "días hábiles" if tipo == "habiles" else "días calendario"
                extra = f"Plazo máximo fijado: {crono['plazo_maximo']} {u}"
            if (crono.get("frentes") or 0) > 1:
                extra = (extra + "   ·   " if extra else "") + f"{crono['frentes']} frentes · {crono.get('personal_total', 0)} personas"
            ruta = _ruta_critica(crono, flecha, ANCHO * 0.50, cursiva, 7.5)
            c.setFillColor(colors.black); c.setFont(negrita, 9.5)
            ancho_nombre = ANCHO - (stringWidth(_limpio(ruta), cursiva, 7.5) if ruta else 0) - 14
            c.drawString(M, y - 56, _recortar("Proyecto: " + str(proyecto.get("nombre", "")), negrita, 9.5, ancho_nombre))
            if ruta:
                c.setFillColor(ROJO); c.setFont(cursiva, 7.5)
                c.drawRightString(M + ANCHO, y - 56, _limpio(ruta))
            c.setFillColor(GRIS_TEXTO); c.setFont(normal, 8)
            linea2 = []
            if empresa:
                linea2.append(f"Contratista: {empresa}")
            if proyecto.get("entidad"):
                linea2.append(f"Entidad: {proyecto['entidad']}")
            if linea2:
                c.drawString(M, y - 68, _recortar("   ·   ".join(linea2), normal, 8, ANCHO * 0.62))
            fin_txt = _dmy(_a_fecha(crono["fecha_fin"])) if crono.get("fecha_fin") else "—"
            c.drawRightString(M + ANCHO, y - 68, _limpio(f"Inicio: {_dmy(inicio)}   ·   Fin: {fin_txt}" + (f"   ·   {extra}" if extra else "")))
            y -= ALTO_TITULO_P1 - 8
        else:
            c.setFillColor(AZUL_TITULO); c.setFont(negrita, 10)
            c.drawString(M, y - 12, "CRONOGRAMA DE ACTIVIDADES")
            c.setFillColor(GRIS_TEXTO); c.setFont(normal, 8)
            c.drawRightString(M + ANCHO, y - 12, _recortar(str(proyecto.get("nombre", "")), normal, 8, ANCHO * 0.7))
            y -= ALTO_TITULO_PN

        # ---- cabecera de la tabla y de la escala ----
        top_cab = y
        base = top_cab - ALTO_CAB
        c.setFillColor(CAB_FONDO); c.setStrokeColor(AZUL_BORDE); c.setLineWidth(0.8)
        c.rect(M, base, ANCHO, ALTO_CAB, stroke=0, fill=1)
        c.setFillColor(AZUL_TITULO); c.setFont(negrita, 7.5)
        x = M
        for i, (titulo, w) in enumerate(COLS):
            if i == 1:
                c.drawString(x + 4, base + 9, titulo)
            else:
                c.drawCentredString(x + w / 2, base + 9, _limpio(titulo))
            x += w
            c.setStrokeColor(colors.HexColor("#A9BEDB")); c.setLineWidth(0.4)
            c.line(x, base, x, top_cab)
        # escala
        c.setStrokeColor(colors.HexColor("#A9BEDB")); c.setLineWidth(0.4)
        c.line(gx, base + ALTO_CAB / 2, gx + ANCHO_GANTT, base + ALTO_CAB / 2)
        semanas = math.ceil(total / 7)
        if modo_dias:
            for w in range(semanas):
                x0, x1 = x_dia(w * 7 + 1), x_dia(min((w + 1) * 7, total) + 1)
                c.setFillColor(AZUL_TITULO); c.setFont(negrita, 7.5)
                etq = f"Semana {w + 1}" if x1 - x0 > 34 else f"S{w + 1}"
                c.drawCentredString((x0 + x1) / 2, top_cab - 9.5, etq)
                c.setStrokeColor(AZUL_BORDE); c.setLineWidth(0.6)
                c.line(x0, base, x0, top_cab)
            c.setFont(normal, 6.3)
            for d in range(1, total + 1):
                c.setFillColor(GRIS_TEXTO)
                c.drawCentredString(x_dia(d) + dpx / 2, base + 3.5, str(d))
        else:
            # meses arriba (por fecha real) y semanas abajo
            d = 1
            while d <= total:
                f_ = inicio + timedelta(days=d - 1)
                sig_mes = date(f_.year + (f_.month == 12), f_.month % 12 + 1, 1)
                d_fin = min(total, (sig_mes - inicio).days)
                x0, x1 = x_dia(d), x_dia(d_fin + 1)
                etq = f"{MESES[f_.month - 1]} {f_.year}" if x1 - x0 > 44 else (MESES[f_.month - 1] if x1 - x0 > 16 else "")
                c.setFillColor(AZUL_TITULO); c.setFont(negrita, 7.2)
                if etq:
                    c.drawCentredString((x0 + x1) / 2, top_cab - 9.5, etq)
                c.setStrokeColor(AZUL_BORDE); c.setLineWidth(0.5)
                c.line(x0, top_cab - ALTO_CAB / 2, x0, top_cab)
                d = d_fin + 1
            paso = max(1, math.ceil(16 / (7 * dpx)))
            c.setFont(normal, 6.3)
            for w in range(0, semanas, paso):
                etq = f"S{w + 1}"
                if x_dia(w * 7 + 1) + 1.5 + stringWidth(etq, normal, 6.3) > gx + ANCHO_GANTT:
                    break
                c.setFillColor(GRIS_TEXTO)
                c.drawString(x_dia(w * 7 + 1) + 1.5, base + 3.5, etq)
        # ---- cuerpo ----
        y0 = base
        alto_cuerpo = len(pag) * ALTO_FILA
        # sombreado de días no laborables y cuadrícula
        for d in range(1, total + 1):
            if d in nolab:
                c.setFillColor(GRIS_NOLAB)
                c.rect(x_dia(d), y0 - alto_cuerpo, dpx, alto_cuerpo, stroke=0, fill=1)
        c.setStrokeColor(GRIS_GRILLA); c.setLineWidth(0.3)
        if modo_dias:
            for d in range(1, total + 2):
                c.line(x_dia(d), y0, x_dia(d), y0 - alto_cuerpo)
        else:
            for w in range(semanas + 1):
                if w * 7 + 1 <= total + 1:  # nunca fuera del cuadro del Gantt
                    c.line(x_dia(w * 7 + 1), y0, x_dia(w * 7 + 1), y0 - alto_cuerpo)
        pos: dict[int, float] = {}  # Id de fila -> y del centro (solo las de esta página)
        for i, f in enumerate(pag):
            yt = y0 - i * ALTO_FILA
            yc = yt - ALTO_FILA / 2
            pos[f.id] = yc
            if i % 2 == 1:
                c.setFillColor(BANDA)
                c.rect(M, yt - ALTO_FILA, ANCHO_TABLA, ALTO_FILA, stroke=0, fill=1)
            color = ROJO if (f.critica and f.tipo != "modulo") else colors.black
            c.setFillColor(color)
            fuente = negrita if f.tipo == "modulo" else normal
            c.setFont(fuente, 7)
            ty = yc - 2.4
            x = M
            c.setFillColor(GRIS_TEXTO if not f.critica else ROJO)
            c.drawCentredString(x + COLS[0][1] / 2, ty, str(f.id)); x += COLS[0][1]
            c.setFillColor(color)
            ancho_nombre = COLS[1][1] - 6 - 6 * (f.sangria or 0)
            if f.etiqueta:  # frente de trabajo, a la derecha de la celda
                c.setFont(negrita, 6.3); c.setFillColor(AZUL_BARRA)
                c.drawRightString(x + COLS[1][1] - 3, ty, f.etiqueta)
                ancho_nombre -= stringWidth(f.etiqueta, negrita, 6.3) + 4
                c.setFont(fuente, 7); c.setFillColor(color)
            c.drawString(x + 3 + 6 * (f.sangria or 0), ty, _recortar(f.nombre, fuente, 7, ancho_nombre)); x += COLS[1][1]
            for texto, w in ((_dias(f.dur), COLS[2][1]), (f"Día {f.ini}", COLS[3][1]), (f"Día {f.fin}", COLS[4][1]),
                             (";".join(str(p) for p in f.preds), COLS[5][1])):
                c.drawCentredString(x + w / 2, ty, _recortar(texto, fuente, 7, w - 3)); x += w
        # marco y líneas de la tabla
        c.setStrokeColor(AZUL_BORDE); c.setLineWidth(1)
        c.rect(M, y0 - alto_cuerpo, ANCHO, alto_cuerpo + ALTO_CAB, stroke=1, fill=0)
        c.setLineWidth(0.4); c.setStrokeColor(colors.HexColor("#A9BEDB"))
        x = M
        for _, w in COLS:
            x += w
            c.line(x, y0 - alto_cuerpo, x, y0)
        c.setStrokeColor(AZUL_BORDE); c.setLineWidth(1)
        c.line(gx, y0 - alto_cuerpo, gx, top_cab)
        c.line(M, base, M + ANCHO, base)

        # ---- barras ----
        alto_barra = ALTO_FILA - 4.4
        extremos: dict[int, tuple[float, float]] = {}  # Id -> (x inicio, x fin)
        for f in pag:
            yc = pos[f.id]
            x_i, x_f = x_dia(f.ini), x_dia(f.fin + 1)
            extremos[f.id] = (x_i, x_f)
            if f.tipo == "tarea":
                c.setFillColor(ROJO_RELLENO if f.critica else AZUL_RELLENO)
                c.setStrokeColor(ROJO if f.critica else AZUL_BARRA); c.setLineWidth(0.8)
                c.rect(x_i, yc - alto_barra / 2, max(x_f - x_i, 1.2), alto_barra, stroke=1, fill=1)
            elif f.tipo == "modulo":
                c.setFillColor(GRIS_RESUMEN)
                c.rect(x_i, yc + 1, max(x_f - x_i, 1.2), 3.6, stroke=0, fill=1)
                for xe, signo in ((x_i, 1), (x_f, -1)):  # puntas hacia abajo, como en Project
                    p = c.beginPath()
                    p.moveTo(xe, yc + 1); p.lineTo(xe + signo * 3.6, yc + 1); p.lineTo(xe, yc - 3.2); p.close()
                    c.drawPath(p, stroke=0, fill=1)
            else:  # hito
                cx = x_i + dpx / 2 if modo_dias else x_i
                extremos[f.id] = (cx - 4, cx + 4)
                c.setFillColor(ROJO); c.setStrokeColor(ROJO)
                p = c.beginPath()
                p.moveTo(cx - 4.4, yc); p.lineTo(cx, yc + 4.4); p.lineTo(cx + 4.4, yc); p.lineTo(cx, yc - 4.4); p.close()
                c.drawPath(p, stroke=0, fill=1)
        # ---- dependencias (fin-inicio) ----
        criticas = {g.id: g.critica for g in pag}
        enlaces = [(f, pid) for f in pag for pid in f.preds if pid in pos]  # si el predecesor está en otra página, no se dibuja
        enlaces.sort(key=lambda e: bool(criticas[e[1]] and e[0].critica))  # las rojas al final, para que queden encima
        for f, pid in enlaces:
            if True:
                xp = extremos[pid][1]
                xs = extremos[f.id][0]
                yp, ys = pos[pid], pos[f.id]
                roja = criticas[pid] and f.critica
                c.setStrokeColor(ROJO if roja else GRIS_DEP); c.setFillColor(ROJO if roja else GRIS_DEP)
                c.setLineWidth(0.7)
                xm = xp + min(3.0, max(xs - xp, 0) / 2)
                p = c.beginPath()
                p.moveTo(xp, yp); p.lineTo(xm, yp); p.lineTo(xm, ys); p.lineTo(max(xs - 2.6, xm), ys)
                c.drawPath(p, stroke=1, fill=0)
                fl = c.beginPath()
                fl.moveTo(xs, ys); fl.lineTo(xs - 3.2, ys + 1.8); fl.lineTo(xs - 3.2, ys - 1.8); fl.close()
                c.drawPath(fl, stroke=0, fill=1)
        # ---- etiquetas de duración (después, para que queden por encima de las flechas) ----
        c.setFont(normal, 6.4)
        for f in pag:
            if f.tipo == "modulo":
                continue
            yc = pos[f.id]
            x_i, x_f = extremos[f.id]
            if f.tipo == "hito":
                c.setFillColor(ROJO); c.setFont(negrita, 6.8)
                txt = "Fin de obra"
                if x_i - stringWidth(txt, negrita, 6.8) - 6 > gx:
                    c.drawRightString(x_i - 3, yc - 2.2, txt)
                continue
            txt = _dias(f.dur)
            w_txt = stringWidth(txt, negrita, 6.4)
            if x_f - x_i > w_txt + 5:
                c.setFillColor(ROJO if f.critica else AZUL_TITULO); c.setFont(negrita, 6.4)
                c.drawCentredString((x_i + x_f) / 2, yc - 2.2, txt)
            else:
                c.setFillColor(GRIS_TEXTO); c.setFont(normal, 6.4)
                if x_f + 3 + w_txt <= gx + ANCHO_GANTT:
                    c.drawString(x_f + 3, yc - 2.2, txt)
                else:
                    c.drawRightString(x_i - 3, yc - 2.2, txt)

        # ---- leyenda y pie ----
        yl = M + 30
        c.setFont(normal, 7.5)
        centro = PAG[0] / 2
        items = [("tarea", "Tarea"), ("crit", "Tarea crítica (ruta crítica, holgura 0)"), ("res", "Resumen de módulo"),
                 ("hito", "Hito"), ("dep", "Dependencia (fin-inicio)")]
        anchos = [stringWidth(t, normal, 7.5) + 30 for _, t in items]
        x = centro - (sum(anchos) + 14 * (len(items) - 1)) / 2
        for (clave, texto), w in zip(items, anchos):
            if clave == "tarea":
                c.setFillColor(AZUL_RELLENO); c.setStrokeColor(AZUL_BARRA); c.setLineWidth(0.8); c.rect(x, yl - 2, 20, 8, stroke=1, fill=1)
            elif clave == "crit":
                c.setFillColor(ROJO_RELLENO); c.setStrokeColor(ROJO); c.setLineWidth(0.8); c.rect(x, yl - 2, 20, 8, stroke=1, fill=1)
            elif clave == "res":
                c.setFillColor(GRIS_RESUMEN); c.rect(x, yl + 2, 20, 3.6, stroke=0, fill=1)
            elif clave == "hito":
                c.setFillColor(ROJO); p = c.beginPath()
                p.moveTo(x + 4, yl + 2); p.lineTo(x + 8.5, yl + 6.5); p.lineTo(x + 13, yl + 2); p.lineTo(x + 8.5, yl - 2.5); p.close()
                c.drawPath(p, stroke=0, fill=1)
            else:
                c.setStrokeColor(GRIS_DEP); c.setFillColor(GRIS_DEP); c.setLineWidth(0.7); c.line(x, yl + 2, x + 17, yl + 2)
                fl = c.beginPath(); fl.moveTo(x + 20, yl + 2); fl.lineTo(x + 16.8, yl + 3.8); fl.lineTo(x + 16.8, yl + 0.2); fl.close()
                c.drawPath(fl, stroke=0, fill=1)
            c.setFillColor(GRIS_TEXTO); c.setFont(normal, 7.5)
            c.drawString(x + 25, yl, _limpio(texto))
            x += w + 14
        c.setFillColor(GRIS_TEXTO); c.setFont(cursiva, 6.5)
        c.drawCentredString(centro, yl - 11, _limpio(
            "Duración en días hábiles. Comienzo y Fin: día calendario desde el inicio de obra (día 1). Las zonas grises son días no laborables."
            + (" F1, F2…: frente de trabajo (cada frente hace sus tareas en orden)." if (crono.get("frentes") or 0) > 1 else "")))
        c.setFont(normal, 7.5)
        c.drawString(M, M - 4, _limpio(empresa or "RinoCost"))
        c.drawRightString(M + ANCHO, M - 4, _limpio(f"Plazo de ejecución: {plazo_txt.lower()}   ·   Página {n_pag} de {len(paginas)}"))
        c.showPage()
    c.save()
    return buf.getvalue()
