"""Normalización de nombres de ítems y recursos de construcción.

Convierte "PROV. Y COLOC. TUBERIA PVC DN 50 DESAGUE" y "Provisión y colocado de tubería PVC DN 50
para desagüe" en formas comparables, y separa las ESPECIFICACIONES CRÍTICAS (espesor, diámetro,
dosificación...) que no deben mezclarse: e=5 cm no es e=15 cm aunque el resto del nombre coincida.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


# ---- abreviaturas y sinónimos del rubro ------------------------------------------------------

_ABREVIATURAS = [
    (re.compile(r"h\s*[°º]\s*a\s*[°º]?"), " hormigon armado "),
    (re.compile(r"h\s*[°º]\s*c\s*[°º]?"), " hormigon ciclopeo "),
    (re.compile(r"\bc\s*/\s*"), " con "),
    (re.compile(r"\bs\s*/\s*"), " sobre "),
    (re.compile(r"\bp\s*/\s*"), " para "),
    (re.compile(r"\bprov\.?(?=\s|$)"), " suministro "),
    (re.compile(r"\bcoloc\.?(?=\s|$)"), " instalacion "),
    (re.compile(r"\binst\.?(?=\s|$)"), " instalacion "),
    (re.compile(r"\binc\.?(?=\s|$)"), " incluye "),
]
_FRASES = [
    (re.compile(r"\bcielo\s+falso\b"), " cielo raso "),
    (re.compile(r"\bmamposteria\s+(?:de\s+)?ladrillo\b"), " muro ladrillo "),
    (re.compile(r"\bmuro\s+(?:de\s+)?ladrillo\b"), " muro ladrillo "),
    (re.compile(r"\bpintura\s+al\s+oleo\b"), " pintura oleo "),
]
_PALABRAS = {
    "concreto": "hormigon", "ceramico": "ceramica", "caneria": "tuberia", "remocion": "retiro",
    "extraccion": "retiro", "provision": "suministro", "colocado": "instalacion", "colocacion": "instalacion",
    "montaje": "instalacion",
}
_VACIAS = {"de", "del", "la", "el", "los", "las", "con", "para", "por", "en", "y", "e", "o", "un", "una", "al",
           "sobre", "sin", "su", "se", "no"}
_IGNORABLES = {"dn", "awg", "psi", "mm", "cm", "kg", "lt", "plg", "pulg", "mm2", "m2", "m3"}  # las cubren las specs
_DEBILES = {"suministro", "instalacion", "incluye", "material", "nacional", "tipo"}  # pesan poco al comparar
PESO_DEBIL = 0.35


# ---- especificaciones críticas ------------------------------------------------------------------

_N = r"(\d+(?:[.,]\d+)?)"


def _num(s: str) -> str:
    return s.replace(",", ".")


def especificaciones_criticas(base: str) -> dict[str, str]:
    """`base` = texto en minúscula y sin tildes."""
    out: dict[str, str] = {}
    m = re.search(rf"\be\s*=\s*{_N}\s*(cm|mm)\b", base) or re.search(rf"\bespesor\s*(?:de\s*)?=?\s*{_N}\s*(cm|mm)\b", base)
    if m:
        mm = float(_num(m.group(1))) * (10 if m.group(2) == "cm" else 1)
        out["espesor"] = f"{mm:g}mm"
    if m := re.search(r"\bdn\s*=?\s*(\d+)\b", base):
        out["dn"] = m.group(1)
    if m := re.search(rf"(?:\bd\s*=\s*|\bdiametro\s*(?:de\s*)?=?\s*|ø\s*)(\d+/\d+|{_N})", base):
        out["diametro"] = _num(m.group(1))
    if m := re.search(r"\b(?:n\s*[°º]?\s*)?(\d+)\s*awg\b", base):
        out["awg"] = m.group(1)
    if m := re.search(rf"\b{_N}\s*mm(?:2|²)", base):
        out["seccion"] = _num(m.group(1))
    if m := re.search(r"\bclase\s*(\d+)\b", base):
        out["clase"] = m.group(1)
    if m := re.search(r"\b(\d{3,4})\s*psi\b", base):
        out["psi"] = m.group(1)
    if m := re.search(r"(?<![\d:])(\d{1,2}\s*:\s*\d(?:\s*:\s*\d)?)(?![\d:])", base):
        out["dosificacion"] = re.sub(r"\s+", "", m.group(1))
    if m := re.search(r"\b(\d+)\s*(?:-|a)\s*(\d+)\s*m\b", base):
        out["profundidad"] = f"{m.group(1)}-{m.group(2)}"
    if m := re.search(r"\b(\d{1,2})\s*h\b", base):
        out["hueco"] = m.group(1)
    if m := re.search(rf"{_N}\s*x\s*{_N}(?:\s*x\s*{_N})?", base):
        out["medida"] = "x".join(_num(g) for g in m.groups() if g)
    if m := re.search(r"\b(\d+)(?:a|\s*amp\w*)\b", base):  # "15A", "15 amp" (no "0 a 2 m")
        out["amperaje"] = m.group(1)
    if m := re.search(r"\b(\d+)\s*v\b", base):
        out["voltaje"] = m.group(1)
    if m := re.search(r"\b(\d+(?:/\d+)?)\s*(?:plg|pulg)\b", base):
        out["pulgadas"] = m.group(1)
    return out


# ---- texto preparado y puntaje ------------------------------------------------------------------


@dataclass(frozen=True)
class Texto:
    original: str
    tokens: tuple[str, ...]
    specs: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def dict_specs(self) -> dict[str, str]:
        return dict(self.specs)


@lru_cache(maxsize=8192)
def preparar(nombre: str) -> Texto:
    base = sin_tildes((nombre or "").lower())
    specs = especificaciones_criticas(base)
    t = base
    for rx, rep in _ABREVIATURAS + _FRASES:
        t = rx.sub(rep, t)
    tokens = []
    for palabra in re.findall(r"[a-z]+", t):
        if len(palabra) < 2 or palabra in _VACIAS:
            continue
        if len(palabra) > 5 and palabra.endswith("es"):
            palabra = palabra[:-2]
        elif len(palabra) > 3 and palabra.endswith("s") and not palabra.endswith("ss"):
            palabra = palabra[:-1]
        palabra = _PALABRAS.get(palabra, palabra)
        if palabra in _IGNORABLES:
            continue
        tokens.append(palabra)
    return Texto(original=nombre, tokens=tuple(tokens), specs=tuple(sorted(specs.items())))


def _peso(token: str) -> float:
    return PESO_DEBIL if token in _DEBILES else 1.0


def _dice(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    total = sum(map(_peso, a)) + sum(map(_peso, b))
    if total == 0:
        return 0.0
    usados: set[int] = set()
    coincide = 0.0
    for t in a:
        mejor, mejor_r = None, 0.0
        for j, u in enumerate(b):
            if j in usados:
                continue
            r = 1.0 if t == u else SequenceMatcher(None, t, u).ratio()
            if r > mejor_r:
                mejor, mejor_r = j, r
        if mejor is not None and mejor_r >= 0.84:  # tolera errores de tipeo (EOLICO / HEOLICO)
            usados.add(mejor)
            coincide += min(_peso(t), _peso(b[mejor])) * (1.0 if mejor_r == 1.0 else 0.9)
    return 2 * coincide / total


@dataclass
class Puntaje:
    valor: float
    conflictos: list[str]
    faltantes: list[str]


ETIQUETAS = {"espesor": "Espesor", "dn": "Diámetro nominal (DN)", "diametro": "Diámetro", "awg": "Calibre AWG",
             "seccion": "Sección", "clase": "Clase", "psi": "Resistencia (psi)", "dosificacion": "Dosificación",
             "profundidad": "Profundidad", "hueco": "Tipo de ladrillo (huecos)", "medida": "Medidas",
             "amperaje": "Amperaje", "voltaje": "Voltaje", "pulgadas": "Pulgadas"}


def puntaje(a: Texto, b: Texto) -> Puntaje:
    """Qué tan parecidos son dos nombres (0 a 1). `a` es lo que se busca y `b` el candidato."""
    sa, sb = a.dict_specs, b.dict_specs
    conflictos = [f"{ETIQUETAS.get(k, k)}: se pide {sa[k]} y el candidato indica {sb[k]}"
                  for k in sa if k in sb and sa[k] != sb[k]]
    faltantes = [f"el candidato no indica {ETIQUETAS.get(k, k).lower()} ({sa[k]})" for k in sa if k not in sb]
    if a.tokens == b.tokens and not conflictos:
        base = 1.0
    else:
        dice = _dice(a.tokens, b.tokens)
        secuencia = SequenceMatcher(None, " ".join(a.tokens), " ".join(b.tokens)).ratio()  # tolera tipeos
        base = 0.65 * dice + 0.35 * secuencia
    valor = max(0.0, base - 0.30 * len(conflictos) - 0.04 * len(faltantes))
    return Puntaje(round(valor, 3), conflictos, faltantes)
