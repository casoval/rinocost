"""Lector del Formulario B-1 (presupuesto por ítems) de convocatorias en PDF.

Reglas de diseño acordadas:
- El B-1 es la fuente de verdad de: número, nombre, unidad, cantidad, orden y módulo.
- Se conserva el texto original; aparte se guarda una versión normalizada.
- Nunca se corrige nada en silencio: lo dudoso se reporta como alerta.
- Dos lecturas independientes (tablas y texto) se comparan entre sí como control.

Uso rápido:
    python -m app.importers.b1_parser ruta/al/b1.pdf
    python -m app.importers.b1_parser ruta/al/b1.pdf --json
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Sequence

# --------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------


@dataclass
class AlertaB1:
    nivel: str  # "error" | "advertencia" | "info"
    codigo: str
    mensaje: str
    item_numero: Optional[int] = None


@dataclass
class ItemB1:
    numero: int  # numeración original del B-1 (continua entre módulos)
    descripcion: str  # texto original en una sola línea
    descripcion_original: str  # texto original con saltos de línea tal como vino
    unidad: str  # unidad tal como viene en el B-1
    unidad_normalizada: str  # solo para comparar con la biblioteca
    cantidad: Optional[Decimal]
    cantidad_texto: str
    orden: int  # posición global en el documento (1, 2, 3...)
    pagina: int
    modulo_codigo: str


@dataclass
class ModuloB1:
    codigo: str  # "M01"
    nombre: str  # "OBRAS PRELIMINARES"
    orden: int
    items: list[ItemB1] = field(default_factory=list)


@dataclass
class ResultadoB1:
    modulos: list[ModuloB1] = field(default_factory=list)
    alertas: list[AlertaB1] = field(default_factory=list)
    estrategia: str = ""

    def items(self) -> list[ItemB1]:
        return [it for m in self.modulos for it in m.items]

    @property
    def total_items(self) -> int:
        return len(self.items())

    def to_dict(self) -> dict:
        def item_dict(it: ItemB1) -> dict:
            return {
                "numero": it.numero,
                "descripcion": it.descripcion,
                "descripcion_original": it.descripcion_original,
                "unidad": it.unidad,
                "unidad_normalizada": it.unidad_normalizada,
                "cantidad": None if it.cantidad is None else str(it.cantidad),
                "cantidad_texto": it.cantidad_texto,
                "orden": it.orden,
                "pagina": it.pagina,
                "modulo_codigo": it.modulo_codigo,
            }

        return {
            "estrategia": self.estrategia,
            "total_items": self.total_items,
            "modulos": [
                {
                    "codigo": m.codigo,
                    "nombre": m.nombre,
                    "orden": m.orden,
                    "items": [item_dict(it) for it in m.items],
                }
                for m in self.modulos
            ],
            "alertas": [
                {
                    "nivel": a.nivel,
                    "codigo": a.codigo,
                    "mensaje": a.mensaje,
                    "item_numero": a.item_numero,
                }
                for a in self.alertas
            ],
        }


# --------------------------------------------------------------------------
# Utilidades de texto, números y unidades
# --------------------------------------------------------------------------


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _clave(texto: str) -> str:
    """Solo letras y números en minúscula y sin tildes. Sirve para comparar."""
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(texto).lower())


_UNIDADES = {
    "m2": "m2", "m²": "m2", "mt2": "m2", "mts2": "m2", "m^2": "m2",
    "m3": "m3", "m³": "m3", "mt3": "m3", "mts3": "m3", "m^3": "m3",
    "m": "m", "ml": "m", "mt": "m", "mts": "m",
    "glb": "glb", "gbl": "glb", "gl": "glb", "global": "glb",
    "pza": "pza", "pzas": "pza", "pieza": "pza", "piezas": "pza",
    "u": "u", "un": "u", "und": "u", "unid": "u", "unidad": "u",
    "kg": "kg", "l": "l", "lt": "l", "lts": "l",
    "dia": "dia", "día": "dia", "dias": "dia", "días": "dia",
    "h": "h", "hr": "h", "hrs": "h",
    "tn": "tn", "ton": "tn",
    "pie2": "pie2", "pie²": "pie2", "p2": "pie2", "gal": "gal", "galon": "gal", "galón": "gal", "hoja": "hoja", "rollo": "rollo", "bolsa": "bolsa", "saco": "saco",
}


def normalizar_unidad(texto: str) -> str:
    t = (texto or "").strip().lower().replace(".", "").replace(" ", "")
    return _UNIDADES.get(t, t)


def unidad_conocida(texto: str) -> bool:
    t = (texto or "").strip().lower().replace(".", "").replace(" ", "")
    return t in _UNIDADES


def parse_cantidad(texto: str) -> Optional[Decimal]:
    """Convierte '32,34', '1.234,56', '1,234.56' o '87.3' en Decimal.

    Convención boliviana: la coma es el decimal. Si solo hay un punto y no
    tiene forma de miles (grupos de 3 dígitos), se toma como decimal.
    """
    t = (texto or "").strip().replace(" ", "").replace("\u00a0", "")
    if not t or not re.fullmatch(r"[\d.,]+", t):
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if t.count(",") > 1 else t.replace(",", ".")
    elif "." in t and re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _unir_lineas(partes: Sequence[str]) -> str:
    """Une líneas partidas. 'Cu-' + 'Unifilar' -> 'Cu-Unifilar' (guion pegado),
    pero 'ARENA -' + 'CEMENTO' -> 'ARENA - CEMENTO' (guion separado)."""
    acumulado = ""
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        if not acumulado:
            acumulado = parte
        elif acumulado.endswith("-") and not acumulado.endswith(" -"):
            acumulado += parte
        else:
            acumulado += " " + parte
    return acumulado


# --------------------------------------------------------------------------
# Constructor común a las dos lecturas
# --------------------------------------------------------------------------

_MODULO_RE = re.compile(r"^\s*>?\s*(M\s?\d+)\s*[-–—:.]\s*(.+?)\s*$", re.IGNORECASE)
_ENTERO_RE = re.compile(r"^\s*(\d{1,4})\s*$")


class _Constructor:
    def __init__(self) -> None:
        self.modulos: list[ModuloB1] = []
        self.alertas: list[AlertaB1] = []
        self._modulo: Optional[ModuloB1] = None
        self._ultimo: Optional[ItemB1] = None
        self._orden = 0

    def alerta(self, nivel: str, codigo: str, mensaje: str, item: Optional[int] = None) -> None:
        self.alertas.append(AlertaB1(nivel, codigo, mensaje, item))

    def abrir_modulo(self, codigo: str, nombre: str) -> None:
        codigo = re.sub(r"\s+", "", codigo).upper()
        self._modulo = ModuloB1(codigo=codigo, nombre=" ".join(nombre.split()), orden=len(self.modulos) + 1)
        self.modulos.append(self._modulo)
        self._ultimo = None

    def agregar_item(
        self, numero: int, descripcion_original: str, unidad: str, cantidad_texto: str, pagina: int
    ) -> ItemB1:
        if self._modulo is None:
            self.abrir_modulo("", "(Sin módulo)")
            self.alerta("info", "item_sin_modulo", "Hay ítems antes del primer módulo; se agruparon en '(Sin módulo)'.")
        self._orden += 1
        item = ItemB1(
            numero=numero,
            descripcion=_unir_lineas(descripcion_original.split("\n")),
            descripcion_original=descripcion_original,
            unidad=unidad.strip(),
            unidad_normalizada=normalizar_unidad(unidad),
            cantidad=parse_cantidad(cantidad_texto),
            cantidad_texto=cantidad_texto.strip(),
            orden=self._orden,
            pagina=pagina,
            modulo_codigo=self._modulo.codigo,
        )
        self._modulo.items.append(item)
        self._ultimo = item
        return item

    def continuar_descripcion(self, texto: str) -> None:
        """Una fila sin número ni unidad que sigue a un ítem: continúa su descripción."""
        it = self._ultimo
        if it is None:
            return
        it.descripcion_original += "\n" + texto.strip()
        it.descripcion = _unir_lineas(it.descripcion_original.split("\n"))

    def resultado(self, estrategia: str) -> ResultadoB1:
        res = ResultadoB1(modulos=self.modulos, alertas=self.alertas, estrategia=estrategia)
        _validar(res)
        return res


# --------------------------------------------------------------------------
# Lectura 1: por tablas (principal)
# --------------------------------------------------------------------------

_CABECERAS = {
    "numero": {"item", "n", "nro", "no", "numero"},
    "descripcion": {"descripcion"},
    "unidad": {"unidad", "und", "unid"},
    "cantidad": {"cantidad", "cant"},
}
_COLUMNAS_POR_DEFECTO = {"numero": 0, "descripcion": 1, "unidad": 2, "cantidad": 3}


def _detectar_cabecera(celdas: Sequence[str]) -> Optional[dict[str, int]]:
    encontrado: dict[str, int] = {}
    for idx, celda in enumerate(celdas):
        clave = _clave(celda)
        for campo, opciones in _CABECERAS.items():
            if clave in opciones and campo not in encontrado:
                encontrado[campo] = idx
    if "descripcion" in encontrado and ("unidad" in encontrado or "cantidad" in encontrado):
        return {**_COLUMNAS_POR_DEFECTO, **encontrado}
    return None


def _celda(celdas: Sequence[str], idx: int) -> str:
    return celdas[idx] if 0 <= idx < len(celdas) else ""


def _procesar_filas_tabla(
    c: _Constructor, filas: Sequence[Sequence[Optional[str]]], pagina: int, cols: dict[str, int]
) -> None:
    for fila in filas:
        celdas = [(x or "").strip() for x in fila]
        if not any(celdas):
            continue

        cab = _detectar_cabecera(celdas)
        if cab:
            cols.clear()
            cols.update(cab)
            continue

        numero_txt = _celda(celdas, cols["numero"])
        es_numero = _ENTERO_RE.match(numero_txt)

        if not es_numero:
            # ¿Fila de módulo? Se mira lo que hay en las primeras dos columnas.
            texto = " ".join(x for x in celdas[:2] if x)
            m = _MODULO_RE.match(texto)
            if m:
                c.abrir_modulo(m.group(1), m.group(2))
                continue
            # ¿Continuación de descripción (sin número, sin unidad ni cantidad)?
            desc = _celda(celdas, cols["descripcion"])
            if (
                desc
                and not numero_txt
                and not _celda(celdas, cols["unidad"])
                and not _celda(celdas, cols["cantidad"])
                and c._ultimo is not None
            ):
                c.continuar_descripcion(desc)
            continue  # títulos, totales y otras filas ajenas se ignoran

        numero = int(es_numero.group(1))
        desc = _celda(celdas, cols["descripcion"])
        unidad = _celda(celdas, cols["unidad"])
        cantidad = _celda(celdas, cols["cantidad"])
        if not desc and not unidad and not cantidad:
            continue
        c.agregar_item(numero, desc, unidad, cantidad, pagina)


def _desde_tablas(paginas: Sequence[tuple[int, list, str]]) -> ResultadoB1:
    c = _Constructor()
    cols = dict(_COLUMNAS_POR_DEFECTO)
    for pagina, tablas, _texto in paginas:
        for tabla in tablas:
            _procesar_filas_tabla(c, tabla, pagina, cols)
    return c.resultado("tablas")


# --------------------------------------------------------------------------
# Lectura 2: por texto (respaldo y verificación cruzada)
# --------------------------------------------------------------------------

_ITEM_TEXTO_RE = re.compile(r"^(\d{1,4})\s+(?:(.*?)\s+)?(\S{1,6})\s+(\d[\d.,]*)$")
_RUIDO_RE = re.compile(
    r"(precio|\(numeral\)|\(literal\)|\bitem\b|ítem descripci|formulario|documento de contrataci"
    r"|vol[uú]menes de obra|\(informaci[oó]n|\(costo|proponente|\(en bolivianos\)|presupuesto por)",
    re.IGNORECASE,
)


def _clasificar_linea(linea: str) -> str:
    if not linea:
        return "vacia"
    if _MODULO_RE.match(linea) and linea.lstrip().startswith(">"):
        return "modulo"
    if _ITEM_TEXTO_RE.match(linea):
        return "item"
    if _RUIDO_RE.search(linea) or re.fullmatch(r"\d+", linea):
        return "ruido"
    return "libre"


def _desde_texto(paginas: Sequence[tuple[int, list, str]]) -> ResultadoB1:
    c = _Constructor()
    for pagina, _tablas, texto in paginas:
        lineas = [x.strip() for x in (texto or "").splitlines()]
        clases = [_clasificar_linea(x) for x in lineas]
        consumidas: set[int] = set()
        for i, (linea, clase) in enumerate(zip(lineas, clases)):
            if clase == "modulo":
                m = _MODULO_RE.match(linea)
                c.abrir_modulo(m.group(1), m.group(2))  # type: ignore[union-attr]
            elif clase == "item":
                m = _ITEM_TEXTO_RE.match(linea)
                numero, desc, unidad, cantidad = m.groups()  # type: ignore[union-attr]
                partes = [desc or ""]
                reconstruida = False
                if not desc:
                    # La descripción quedó partida: línea anterior + línea siguiente.
                    if i > 0 and clases[i - 1] == "libre" and (i - 1) not in consumidas:
                        partes.insert(0, lineas[i - 1])
                        consumidas.add(i - 1)
                        reconstruida = True
                    if i + 1 < len(lineas) and clases[i + 1] == "libre" and (i + 1) not in consumidas:
                        partes.append(lineas[i + 1])
                        consumidas.add(i + 1)
                        reconstruida = True
                it = c.agregar_item(int(numero), "\n".join(p for p in partes if p), unidad, cantidad, pagina)
                if reconstruida:
                    c.alerta(
                        "info",
                        "descripcion_reconstruida",
                        "Descripción reconstruida a partir de líneas vecinas (lectura por texto).",
                        it.numero,
                    )
    return c.resultado("texto")


# --------------------------------------------------------------------------
# Validación y comparación
# --------------------------------------------------------------------------


def _validar(res: ResultadoB1) -> None:
    items = res.items()
    if not items:
        res.alertas.append(AlertaB1("error", "sin_items", "No se encontró ningún ítem en el documento."))
        return

    vistos: set[int] = set()
    esperado = items[0].numero
    for it in items:
        if it.numero in vistos:
            res.alertas.append(AlertaB1("error", "numero_duplicado", f"El ítem {it.numero} aparece más de una vez.", it.numero))
        elif it.numero != esperado:
            res.alertas.append(
                AlertaB1("advertencia", "numeracion_salteada", f"Se esperaba el ítem {esperado} y viene el {it.numero}.", it.numero)
            )
        vistos.add(it.numero)
        esperado = it.numero + 1

        if it.cantidad is None:
            res.alertas.append(
                AlertaB1("error", "cantidad_invalida", f"Cantidad ilegible en el ítem {it.numero}: '{it.cantidad_texto}'.", it.numero)
            )
        elif it.cantidad == 0:
            res.alertas.append(AlertaB1("advertencia", "cantidad_cero", f"El ítem {it.numero} tiene cantidad 0.", it.numero))
        if not it.unidad:
            res.alertas.append(AlertaB1("error", "unidad_vacia", f"El ítem {it.numero} no tiene unidad.", it.numero))
        elif not unidad_conocida(it.unidad):
            res.alertas.append(
                AlertaB1("info", "unidad_desconocida", f"Unidad no reconocida en el ítem {it.numero}: '{it.unidad}'.", it.numero)
            )
        if not it.descripcion:
            res.alertas.append(AlertaB1("error", "descripcion_vacia", f"El ítem {it.numero} no tiene descripción.", it.numero))

    for m in res.modulos:
        if not m.items:
            res.alertas.append(AlertaB1("advertencia", "modulo_vacio", f"El módulo {m.codigo} ({m.nombre}) no tiene ítems."))


def _firma(res: ResultadoB1) -> dict[int, tuple]:
    return {
        it.numero: (_clave(it.descripcion), it.unidad_normalizada, it.cantidad, it.modulo_codigo)
        for it in res.items()
    }


def comparar_lecturas(principal: ResultadoB1, control: ResultadoB1) -> list[AlertaB1]:
    """Compara las dos lecturas. Si coinciden, es una buena señal de que se leyó bien."""
    a, b = _firma(principal), _firma(control)
    alertas: list[AlertaB1] = []
    for n in sorted(set(a) | set(b)):
        if n not in a:
            alertas.append(AlertaB1("advertencia", "lectura_discrepante", f"El ítem {n} solo apareció en la lectura por texto.", n))
        elif n not in b:
            alertas.append(AlertaB1("advertencia", "lectura_discrepante", f"El ítem {n} solo apareció en la lectura por tablas.", n))
        elif a[n] != b[n]:
            alertas.append(AlertaB1("advertencia", "lectura_discrepante", f"El ítem {n} se leyó distinto en tablas y en texto; revisar.", n))
    return alertas


# --------------------------------------------------------------------------
# Punto de entrada
# --------------------------------------------------------------------------


def _extraer_paginas(ruta_pdf: str | Path) -> list[tuple[int, list, str]]:
    import pdfplumber  # import perezoso: el módulo se puede importar sin pdfplumber

    paginas: list[tuple[int, list, str]] = []
    with pdfplumber.open(str(ruta_pdf)) as pdf:
        for page in pdf.pages:
            paginas.append((page.page_number, page.extract_tables(), page.extract_text() or ""))
    return paginas


def parse_b1(ruta_pdf: str | Path, verificar: bool = True) -> ResultadoB1:
    """Lee un Formulario B-1 en PDF y devuelve módulos, ítems y alertas.

    Estrategia: tablas como lectura principal; si no encuentra ítems, usa texto.
    Con verificar=True, compara ambas lecturas y avisa de cualquier diferencia.
    """
    paginas = _extraer_paginas(ruta_pdf)
    por_tablas = _desde_tablas(paginas)

    if por_tablas.total_items == 0:
        por_texto = _desde_texto(paginas)
        por_texto.alertas.insert(
            0, AlertaB1("advertencia", "lectura_por_texto", "No se detectaron tablas; se usó la lectura por texto. Revisar con cuidado.")
        )
        return por_texto

    if verificar:
        por_texto = _desde_texto(paginas)
        if por_texto.total_items == 0:
            por_tablas.alertas.append(
                AlertaB1("info", "sin_verificacion", "La lectura por texto no encontró ítems; no se pudo verificar.")
            )
        else:
            por_tablas.alertas.extend(comparar_lecturas(por_tablas, por_texto))
    return por_tablas


# --------------------------------------------------------------------------
# Línea de comandos
# --------------------------------------------------------------------------


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Lee un Formulario B-1 en PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true", help="imprimir el resultado completo en JSON")
    args = ap.parse_args(argv)

    res = parse_b1(args.pdf)
    if args.json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"Estrategia: {res.estrategia} · módulos: {len(res.modulos)} · ítems: {res.total_items}\n")
    for m in res.modulos:
        print(f"[{m.codigo}] {m.nombre}")
        for it in m.items:
            print(f"   {it.numero:>3}  {it.descripcion[:62]:<62} {it.unidad:>4} {it.cantidad_texto:>8}")
    print("\nAlertas:" if res.alertas else "\nSin alertas.")
    for a in res.alertas:
        print(f"  [{a.nivel}] {a.codigo}: {a.mensaje}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
