"""Lector de especificaciones técnicas por ítem (PDF).

Reglas de diseño acordadas:
- El B-1 manda (nombre, unidad, cantidad, orden, módulo). Las especificaciones solo
  complementan: qué recursos pide cada ítem y qué datos técnicos declara.
- Cada especificación se asigna al ítem del B-1 por NÚMERO de ítem, no por nombre ni módulo.
- Todo dato extraído guarda la página y el fragmento de origen.
- Nunca se corrige nada en silencio: las diferencias se reportan como alertas.
- La especificación dice QUÉ recursos pide, no CUÁNTO: las cantidades quedan pendientes.

Uso rápido:
    python -m app.importers esp ruta/especificaciones.pdf [--b1 ruta/b1.pdf] [--json]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .b1_parser import AlertaB1, _clave, _sin_tildes, normalizar_unidad

# --------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------


@dataclass
class RecursoRequerido:
    tipo: str  # material | mano_obra | equipo
    nombre: str
    unidad: Optional[str]
    unidad_normalizada: Optional[str]
    detalle: Optional[str]  # precisión encontrada en otra mención (p. ej. medidas)
    pagina: int
    fragmento: str  # línea original del PDF


@dataclass
class DatoTecnico:
    tipo: str  # dosificacion | espesor | cemento_minimo | rendimiento_declarado | espera
    valor: str
    fragmento: str
    pagina: int


@dataclass
class EspecItem:
    numero: int
    titulo: str
    unidad_spec: Optional[str]
    modulo_spec: Optional[str]  # solo informativo: el módulo oficial es el del B-1
    pagina_inicio: int
    secciones: dict[str, str] = field(default_factory=dict)
    recursos: list[RecursoRequerido] = field(default_factory=list)
    sin_materiales: bool = False  # la especificación dice "No requiere"
    caracteristicas: list[str] = field(default_factory=list)
    datos_tecnicos: list[DatoTecnico] = field(default_factory=list)


@dataclass
class ResultadoEspecificaciones:
    items: list[EspecItem] = field(default_factory=list)
    alertas: list[AlertaB1] = field(default_factory=list)

    def por_numero(self) -> dict[int, EspecItem]:
        res: dict[int, EspecItem] = {}
        for it in self.items:
            res.setdefault(it.numero, it)  # si un número se repite, manda el primero
        return res

    def to_dict(self) -> dict:
        return {
            "total_items": len(self.items),
            "items": [
                {
                    "numero": it.numero,
                    "titulo": it.titulo,
                    "unidad_spec": it.unidad_spec,
                    "modulo_spec": it.modulo_spec,
                    "pagina_inicio": it.pagina_inicio,
                    "sin_materiales": it.sin_materiales,
                    "recursos": [r.__dict__ for r in it.recursos],
                    "caracteristicas": it.caracteristicas,
                    "datos_tecnicos": [d.__dict__ for d in it.datos_tecnicos],
                }
                for it in self.items
            ],
            "alertas": [a.__dict__ for a in self.alertas],
        }


# --------------------------------------------------------------------------
# Reconocimiento de encabezados
# --------------------------------------------------------------------------

_MODULO_RE = re.compile(r"^\s*MOD\s*-?\s*(\d{1,3})\s*[:.\-–—]?\s*(.+?)\s*$", re.IGNORECASE)
# ITEM N°1 · ITEM 4.- · ITEM N5 · ITEM 6 . - · ÍTEM 12.- · ITEM 18.- . - · ITEM N°24 .-
_ITEM_RE = re.compile(r"^\s*[IÍ]TEM\s*(?:N\s*[°º]?\s*)?(\d{1,3})\b[\s.:\-–—]*(.*?)\s*$", re.IGNORECASE)
_UNIDAD_RE = re.compile(r"^\s*unidad\s*:?\s*(\S.*?)\s*$", re.IGNORECASE)
_SECCION_RE = re.compile(r"^\s*([1-5])\s*[.\-)]?\s*(\S.{0,70}?)\s*:?\s*$")


def _tipo_seccion(titulo: str) -> Optional[str]:
    k = _clave(titulo).replace("0", "o")  # "F0RMA DE PAGO" (con cero) también se reconoce
    if k.startswith(("descripcion", "definicion")):
        return "descripcion"
    if k.startswith("materiales"):
        return "materiales"
    if k.startswith(("procedimiento", "formadeejecucion")):
        return "procedimiento"
    if k.startswith("medicion"):
        return "medicion"
    if k.startswith("formadepago"):
        return "pago"
    return None


# --------------------------------------------------------------------------
# Recursos (materiales, mano de obra y equipo)
# --------------------------------------------------------------------------

_VINETA_RE = re.compile(r"^\s*[-–—•·➢*>]+\s*")
_ETIQUETA_RE = re.compile(
    r"^(?P<cat>materiales(?:\s+m[ií]nimos?)?|mano\s+de\s+obra(?:\s+m[ií]nima)?"
    r"|equipos?(?:\s*(?:o|y)\s*maquinaria)?|maquinaria|herramientas)\s*(?P<dos>:)?\s*(?P<resto>.*)$",
    re.IGNORECASE,
)
_INICIO_PROSA = (
    "el ", "la ", "los ", "las ", "este ", "esta ", "estos ", "estas ", "nota", "para ", "se ", "previamente",
    "además", "todos", "cuando", "si ", "no ", "de ", "en ", "con ", "por ", "un ", "una ", "y ", "dentro",
)
_UNIDAD_FINAL_RE = re.compile(r"[\(\[]\s*([A-Za-z]{1,8}\s?\d?)\s*[\)\]]\s*$")
_STOP = {"de", "del", "la", "el", "los", "las", "con", "para", "tipo", "en", "y", "a", "un", "una"}


def _es_prosa(texto: str) -> bool:
    t = texto.strip().lower()
    return len(t) > 90 or t.endswith(":") or t.startswith(_INICIO_PROSA)


def _categoria(etiqueta: str) -> str:
    e = etiqueta.lower()
    if e.startswith("mano"):
        return "mano_obra"
    if e.startswith(("equipo", "maquinaria", "herramienta")):
        return "equipo"
    return "material"


def _tokens(nombre: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", _sin_tildes(nombre).lower()) if t not in _STOP}


def _limpiar_nombre(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip(" \t.,;:")


def _crear_recurso(
    tipo: str, crudo: str, pagina: int, fragmento: str, capitalizar: bool = False
) -> list[RecursoRequerido]:
    texto = _limpiar_nombre(crudo)
    if not texto or _clave(texto) in {"norequiere", "ninguno", "nada"}:
        return []
    partes = [texto]
    if tipo == "mano_obra":
        partes = re.split(r"\s*,\s*|\s+y\s+", texto, flags=re.IGNORECASE)
    elif tipo == "equipo":
        partes = re.split(r"\s*,\s*", texto)
    recursos = []
    for parte in partes:
        parte = _limpiar_nombre(parte)
        if not parte:
            continue
        unidad = None
        m = _UNIDAD_FINAL_RE.search(parte)
        if m:
            unidad = re.sub(r"\s+", " ", m.group(1)).strip()
            parte = _limpiar_nombre(parte[: m.start()])
        if parte:
            if capitalizar:
                parte = parte[0].upper() + parte[1:]
            recursos.append(
                RecursoRequerido(
                    tipo=tipo, nombre=parte, unidad=unidad,
                    unidad_normalizada=normalizar_unidad(unidad) if unidad else None,
                    detalle=None, pagina=pagina, fragmento=fragmento,
                )
            )
    return recursos


def _agregar_sin_duplicar(lista: list[RecursoRequerido], nuevo: RecursoRequerido) -> None:
    """Une menciones repetidas. Mano de obra y equipo: solo si el nombre es el mismo.
    Materiales: también si uno es una precisión del otro (p. ej. + medidas)."""
    tn = _tokens(nuevo.nombre)
    for ex in lista:
        if ex.tipo != nuevo.tipo:
            continue
        te = _tokens(ex.nombre)
        igual = te == tn
        refina = ex.tipo == "material" and te and tn and (te <= tn or tn <= te)
        if igual or refina:
            if refina and not igual and len(nuevo.nombre) > len(ex.nombre) and not ex.detalle:
                ex.detalle = nuevo.nombre
            if ex.unidad is None and nuevo.unidad is not None:
                ex.unidad, ex.unidad_normalizada = nuevo.unidad, nuevo.unidad_normalizada
            return
    lista.append(nuevo)


def _leer_recursos(lineas: Sequence[tuple[int, str]]) -> tuple[list[RecursoRequerido], list[str], bool]:
    """Recorre la sección 'Materiales, herramientas y equipo' con una pequeña máquina de estados."""
    recursos: list[RecursoRequerido] = []
    caracteristicas: list[str] = []
    sin_materiales = False
    estado: Optional[str] = None  # material | mano_obra | equipo | caracteristicas

    for pagina, linea in lineas:
        m = _VINETA_RE.match(linea)
        vineta = m is not None
        texto = linea[m.end():] if m else linea.strip()
        texto = texto.strip()
        if not texto:
            continue

        if not vineta:
            et = _ETIQUETA_RE.match(texto)
            if et:
                cat = _categoria(et.group("cat"))
                resto = et.group("resto").strip()
                estado = cat
                # Texto en la misma línea: "Mano de obra peón." / "Mano de Obra: Albañil, Ayudante"
                inline_ok = (cat == "mano_obra" and len(resto.split()) <= 8) or bool(et.group("dos"))
                if resto and inline_ok:
                    for r in _crear_recurso(cat, resto, pagina, linea, capitalizar=True):
                        _agregar_sin_duplicar(recursos, r)
                continue
            if re.search(r"caracter[ií]sticas\s+m[ií]nimas?", texto, re.IGNORECASE) and texto.endswith((":", ".")):
                estado = "caracteristicas"
                continue
            if "materiales" in texto.lower() and texto.endswith(":"):
                estado = "material"  # "se empleará materiales como ser:" / "los siguientes materiales mínimos:"
                continue

        if estado in ("material", "mano_obra", "equipo"):
            if vineta and len(texto) <= 110:
                if _clave(texto) == "norequiere":
                    sin_materiales = True
                for r in _crear_recurso(estado, texto, pagina, linea.strip()):
                    _agregar_sin_duplicar(recursos, r)
            elif not vineta and not _es_prosa(texto):
                for r in _crear_recurso(estado, texto, pagina, linea.strip()):
                    _agregar_sin_duplicar(recursos, r)
            else:
                estado = None
        elif estado == "caracteristicas":
            if vineta:
                caracteristicas.append(_limpiar_nombre(texto))
            else:
                estado = None
    return recursos, caracteristicas, sin_materiales


# --------------------------------------------------------------------------
# Datos técnicos declarados en el texto (dosificaciones, espesores, esperas...)
# --------------------------------------------------------------------------

_NUM = r"\d+(?:[.,]\d+)?"
_DOSIF_RE = re.compile(r"(?<![\d:])(\d{1,2}\s*:\s*\d(?:[.,]\d)?(?:\s*:\s*\d(?:[.,]\d)?)?)(?![\d:])")
_DOSIF_CONTEXTO_RE = re.compile(r"proporci|dosific|mezcla|mortero|hormig", re.IGNORECASE)
_ESPESOR_RES = [
    re.compile(rf"espesor\b[^.\d]{{0,30}}?({_NUM})\s*(cm|mm)\b", re.IGNORECASE),
    re.compile(rf"\be\s*=\s*({_NUM})\s*(cm|mm)\b", re.IGNORECASE),
]
_REND_RE = re.compile(rf"rendimiento\s*:?\s*({_NUM}\s*(?:m2|m²|m3|m³|ml|m)\s+por\s+[^,.;]{{1,40}})", re.IGNORECASE)
_CEMENTO_MIN_RE = re.compile(
    rf"contenido\s+m[ií]nimo\s+de\s+cemento\s+de\s+({_NUM})\s*(?:kilogramos|kg)\s+por\s+metro\s+c[uú]bico", re.IGNORECASE
)
_RANGO = r"(\d+(?:\s*a\s*\d+)?)\s*(d[ií]as|horas)"
_ESPERA_RES = [
    re.compile(rf"durante\s+(?:las\s+primeras\s+)?{_RANGO}", re.IGNORECASE),
    re.compile(rf"(?:luego\s+de|despu[eé]s\s+de(?:\s+transcurridas)?|transcurridas)\s+{_RANGO}", re.IGNORECASE),
    re.compile(rf"secado\s+[^.]{{0,40}}?de\s+{_RANGO}", re.IGNORECASE),
]


def _recortar(texto: str, largo: int = 200) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _buscar_datos(lineas: Sequence[tuple[int, str]]) -> list[DatoTecnico]:
    encontrados: dict[tuple[str, str], DatoTecnico] = {}

    def agregar(tipo: str, valor: str, fragmento: str, pagina: int) -> None:
        encontrados.setdefault((tipo, valor.lower()), DatoTecnico(tipo, valor, _recortar(fragmento), pagina))

    # Cada línea sola y también unida con la siguiente (las frases se parten entre líneas).
    candidatos = []
    for i, (pag, lin) in enumerate(lineas):
        candidatos.append((pag, lin))
        if i + 1 < len(lineas):
            candidatos.append((pag, lin + " " + lineas[i + 1][1]))

    for pag, texto in candidatos:
        if _DOSIF_CONTEXTO_RE.search(texto):
            for m in _DOSIF_RE.finditer(texto):
                agregar("dosificacion", re.sub(r"\s+", "", m.group(1)), texto, pag)
        for rx in _ESPESOR_RES:
            for m in rx.finditer(texto):
                agregar("espesor", f"{m.group(1)} {m.group(2).lower()}", texto, pag)
        for m in _REND_RE.finditer(texto):
            agregar("rendimiento_declarado", re.sub(r"\s+", " ", m.group(1)).strip(), texto, pag)
        for m in _CEMENTO_MIN_RE.finditer(texto):
            agregar("cemento_minimo", f"{m.group(1)} kg/m3", texto, pag)
        for rx in _ESPERA_RES:
            for m in rx.finditer(texto):
                cantidad = re.sub(r"\s+", " ", m.group(1))
                unidad = m.group(2).lower().replace("í", "i")
                agregar("espera", f"{cantidad} {unidad}", texto, pag)
    return list(encontrados.values())


# --------------------------------------------------------------------------
# Lectura del PDF
# --------------------------------------------------------------------------


def _extraer_paginas_texto(ruta_pdf: str | Path) -> list[tuple[int, str]]:
    import pdfplumber  # import perezoso

    with pdfplumber.open(str(ruta_pdf)) as pdf:
        return [(p.page_number, p.extract_text() or "") for p in pdf.pages]


def _lineas_limpias(paginas: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    """Quita el encabezado repetido ('Especificaciones Técnicas') y el número de página al pie."""
    salida: list[tuple[int, str]] = []
    for num, texto in paginas:
        lineas = [x.strip() for x in texto.splitlines() if x.strip()]
        if lineas and _clave(lineas[0]) == "especificacionestecnicas":
            lineas = lineas[1:]
        if lineas and re.fullmatch(r"\d{1,3}", lineas[-1]):
            lineas = lineas[:-1]
        salida.extend((num, x) for x in lineas)
    return salida


class _Borrador:
    def __init__(self, numero: int, titulo: str, pagina: int, modulo: Optional[str]) -> None:
        self.numero, self.titulo, self.pagina, self.modulo = numero, titulo, pagina, modulo
        self.unidad: Optional[str] = None
        self.seccion: Optional[str] = None
        self.lineas: dict[str, list[tuple[int, str]]] = {}


# Unidades que no tienen sentido para ciertos materiales (cemento en m3, arena en kg...).
_UNIDADES_RARAS = (
    (("cemento", "yeso", "cal"), {"m3", "m2", "l"}),
    (("arena", "grava", "ripio", "piedra"), {"kg", "l", "pza"}),
)


def _alertas_de_unidad(item: EspecItem) -> list[AlertaB1]:
    alertas = []
    for r in item.recursos:
        if r.tipo != "material" or not r.unidad_normalizada:
            continue
        primera = _clave(r.nombre.split()[0]) if r.nombre.split() else ""
        for nombres, malas in _UNIDADES_RARAS:
            if primera in nombres and r.unidad_normalizada in malas:
                alertas.append(
                    AlertaB1(
                        "advertencia", "unidad_sospechosa",
                        f"Ítem {item.numero}: '{r.nombre}' viene en '{r.unidad}' (p. {r.pagina}); parece una unidad poco "
                        "habitual para ese material. Revisar.",
                        item.numero,
                    )
                )
    return alertas


def _cerrar(b: _Borrador, res: ResultadoEspecificaciones) -> None:
    item = EspecItem(
        numero=b.numero, titulo=re.sub(r"\s+", " ", b.titulo).strip(), unidad_spec=b.unidad, modulo_spec=b.modulo,
        pagina_inicio=b.pagina,
        secciones={k: " ".join(x for _, x in v) for k, v in b.lineas.items() if k != "materiales"},
    )
    if "materiales" in b.lineas:
        item.recursos, item.caracteristicas, item.sin_materiales = _leer_recursos(b.lineas["materiales"])
    else:
        res.alertas.append(
            AlertaB1("advertencia", "sin_seccion_recursos",
                     f"Ítem {item.numero}: no se encontró la sección de materiales, mano de obra y equipo.", item.numero)
        )
    texto_util = [x for sec in ("descripcion", "materiales", "procedimiento") for x in b.lineas.get(sec, [])]
    item.datos_tecnicos = _buscar_datos(texto_util)
    res.alertas.extend(_alertas_de_unidad(item))
    if item.numero in {i.numero for i in res.items}:
        res.alertas.append(
            AlertaB1("error", "numero_duplicado", f"El ítem {item.numero} aparece más de una vez en las especificaciones.", item.numero)
        )
    res.items.append(item)


def _parsear(paginas: Sequence[tuple[int, str]]) -> ResultadoEspecificaciones:
    res = ResultadoEspecificaciones()
    modulo: Optional[str] = None
    actual: Optional[_Borrador] = None

    for pagina, linea in _lineas_limpias(paginas):
        mm = _MODULO_RE.match(linea)
        if mm:
            modulo = f"MOD-{int(mm.group(1))} {mm.group(2)}"
            continue
        mi = _ITEM_RE.match(linea)
        if mi:
            if actual:
                _cerrar(actual, res)
            actual = _Borrador(int(mi.group(1)), mi.group(2), pagina, modulo)
            continue
        if actual is None:
            continue
        if actual.seccion is None:
            mu = _UNIDAD_RE.match(linea)
            if mu and actual.unidad is None:
                actual.unidad = mu.group(1)
                continue
        ms = _SECCION_RE.match(linea)
        if ms:
            tipo = _tipo_seccion(ms.group(2))
            if tipo and tipo not in actual.lineas:
                actual.seccion = tipo
                actual.lineas[tipo] = []
                continue
        if actual.seccion is None:
            if actual.unidad is None:  # título del ítem partido en dos líneas
                actual.titulo = f"{actual.titulo} {linea}"
            continue
        actual.lineas[actual.seccion].append((pagina, linea))

    if actual:
        _cerrar(actual, res)
    if not res.items:
        res.alertas.append(AlertaB1("error", "sin_items", "No se encontró ningún ítem en las especificaciones."))
    return res


def parse_especificaciones(ruta_pdf: str | Path) -> ResultadoEspecificaciones:
    """Lee el PDF de especificaciones técnicas y devuelve, por ítem, recursos y datos técnicos."""
    return _parsear(_extraer_paginas_texto(ruta_pdf))


# --------------------------------------------------------------------------
# Cruce con el B-1 (el B-1 manda)
# --------------------------------------------------------------------------


def cruzar_con_b1(esp: ResultadoEspecificaciones, items_b1: Iterable[Any]) -> list[AlertaB1]:
    """Compara especificaciones y B-1 por número de ítem. Acepta ítems del lector (ItemB1)
    o de la base de datos (Item): solo usa numero, descripcion, unidad y unidad_normalizada."""
    alertas: list[AlertaB1] = []
    del_b1 = {}
    for it in items_b1:
        del_b1.setdefault(it.numero, it)
    de_spec = esp.por_numero()

    for n in sorted(del_b1):
        if n not in de_spec:
            alertas.append(AlertaB1("advertencia", "item_sin_especificacion",
                                    f"El ítem {n} del B-1 no tiene especificación técnica.", n))
    for n in sorted(de_spec):
        if n not in del_b1:
            alertas.append(AlertaB1("advertencia", "especificacion_sin_item",
                                    f"Hay especificación del ítem {n}, pero ese ítem no está en el B-1. Se ignora.", n))
    for n in sorted(set(del_b1) & set(de_spec)):
        b1, sp = del_b1[n], de_spec[n]
        if sp.unidad_spec and normalizar_unidad(sp.unidad_spec) != b1.unidad_normalizada:
            alertas.append(AlertaB1(
                "advertencia", "unidad_distinta",
                f"Ítem {n}: el B-1 pide '{b1.unidad}' y la especificación indica '{sp.unidad_spec}'. "
                f"Se usa la del B-1: el APU debe estar expresado en '{b1.unidad}'.", n))
        if SequenceMatcher(None, _clave(b1.descripcion), _clave(sp.titulo)).ratio() < 0.9:
            alertas.append(AlertaB1(
                "info", "nombre_distinto",
                f"Ítem {n}: el nombre en la especificación difiere del B-1 ('{sp.titulo}'). Se mantiene el del B-1.", n))
    return alertas


# --------------------------------------------------------------------------
# Línea de comandos
# --------------------------------------------------------------------------


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Lee las especificaciones técnicas en PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--b1", help="PDF del B-1 para cruzar por número de ítem")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = parse_especificaciones(args.pdf)
    if args.b1:
        from .b1_parser import parse_b1

        res.alertas.extend(cruzar_con_b1(res, parse_b1(args.b1).items()))
    if args.json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return 0

    rotulo = {"material": "Mat", "mano_obra": "M.O.", "equipo": "Eq."}
    print(f"Ítems con especificación: {len(res.items)}\n")
    for it in res.items:
        print(f"{it.numero:>3}. {it.titulo[:70]}  [{it.unidad_spec}]  (p. {it.pagina_inicio})")
        if it.sin_materiales:
            print("       Materiales: no requiere")
        for r in it.recursos:
            u = f" ({r.unidad})" if r.unidad else ""
            print(f"       {rotulo[r.tipo]:<4} {r.nombre}{u}")
        for c in it.caracteristicas:
            print(f"       ·    {c}")
        for d in it.datos_tecnicos:
            print(f"       dato {d.tipo}: {d.valor}")
    print("\nAlertas:" if res.alertas else "\nSin alertas.")
    for a in res.alertas:
        print(f"  [{a.nivel}] {a.codigo}: {a.mensaje}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
