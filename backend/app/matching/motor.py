"""Motor de coincidencia: sugiere qué APU o recurso de la biblioteca corresponde a un ítem o requisito.

Reglas acordadas:
- La unidad del B-1 filtra: un APU en otra unidad nunca pasa de confianza "baja".
- Una especificación crítica distinta (espesor, DN...) impide la confianza "alta".
- Las equivalencias que el usuario ya confirmó tienen prioridad (confianza "alta").
- Solo la confianza "alta" se aplica sola; el resto lo confirma la persona.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from .texto import Texto, preparar, puntaje

UMBRAL_ALTA, UMBRAL_MEDIA, UMBRAL_BAJA = 0.88, 0.62, 0.40
ORDEN_CONFIANZA = {"baja": 0, "media": 1, "alta": 2}


@dataclass(frozen=True)
class ApuRef:
    id: int
    nombre: str
    unidad_normalizada: str


@dataclass
class Candidato:
    apu_id: int
    nombre: str
    unidad_normalizada: str
    puntaje: float
    confianza: str  # alta | media | baja
    motivo: str  # equivalencia | texto
    compatible_unidad: bool
    avisos: list[str] = field(default_factory=list)


def clave_equivalencia(nombre: str, unidad_normalizada: str) -> str:
    """Identifica un ítem para recordar el vínculo confirmado (incluye specs y unidad)."""
    t = preparar(nombre)
    specs = ";".join(f"{k}={v}" for k, v in t.specs)
    return f"{' '.join(t.tokens)}|{specs}|{unidad_normalizada}"


def _confianza(valor: float, conflictos: list[str], compatible: bool, equivalencia: bool) -> str:
    if equivalencia and compatible and not conflictos:
        return "alta"
    if not compatible:
        return "baja" if valor >= UMBRAL_BAJA else "ninguna"
    if valor >= UMBRAL_ALTA and not conflictos:
        return "alta"
    if valor >= UMBRAL_MEDIA:
        return "media"
    return "baja" if valor >= UMBRAL_BAJA else "ninguna"


def sugerir(
    nombre: str,
    unidad_normalizada: str,
    apus: Sequence[ApuRef],
    equivalencias: Optional[Mapping[str, int]] = None,
    maximo: int = 5,
) -> list[Candidato]:
    """Devuelve los mejores candidatos, ordenados: primero los que tienen la unidad del ítem."""
    buscado = preparar(nombre)
    apu_conocido = (equivalencias or {}).get(clave_equivalencia(nombre, unidad_normalizada))
    candidatos: list[Candidato] = []
    for apu in apus:
        p = puntaje(buscado, preparar(apu.nombre))
        compatible = (not apu.unidad_normalizada) or apu.unidad_normalizada == unidad_normalizada
        es_equiv = apu_conocido == apu.id
        valor = 1.0 if es_equiv and not p.conflictos else p.valor
        confianza = _confianza(valor, p.conflictos, compatible, es_equiv)
        if confianza == "ninguna":
            continue
        avisos = list(p.conflictos) + list(p.faltantes)
        if not compatible:
            avisos.insert(0, f"El APU está en '{apu.unidad_normalizada}' y el ítem pide '{unidad_normalizada}'.")
        candidatos.append(Candidato(apu.id, apu.nombre, apu.unidad_normalizada, valor, confianza,
                                    "equivalencia" if es_equiv else "texto", compatible, avisos))

    candidatos.sort(key=lambda c: (not c.compatible_unidad, -c.puntaje))
    # Si dos APU compatibles son casi idénticos, no se decide solo: pasa a "media".
    compat = [c for c in candidatos if c.compatible_unidad]
    if len(compat) >= 2 and compat[0].confianza == "alta" and compat[0].motivo == "texto":
        if compat[1].confianza == "alta" and compat[0].puntaje - compat[1].puntaje < 0.03:
            compat[0].confianza = "media"
            compat[0].avisos.append(f"Hay otro APU casi igual: '{compat[1].nombre}'. Confirma cuál usar.")
    return candidatos[:maximo]


# ---- recursos (requisitos del pliego <-> líneas/recursos de la biblioteca) -------------------------


@dataclass(frozen=True)
class RecursoRef:
    clave: int  # posición o id que identifica al candidato en quien llama
    tipo: str  # material | mano_obra | equipo
    nombre: str
    unidad_normalizada: Optional[str] = None


def _puntaje_recurso(buscado: Texto, cand: Texto, tipo_igual_materiales: bool) -> Optional[float]:
    p = puntaje(buscado, cand)
    if p.conflictos:
        return None
    valor = p.valor
    # Un material con más detalle sigue siendo el mismo ("Cemento portland" ~ "Cemento portland IP-30"),
    # pero solo si el nombre corto tiene al menos 2 palabras ("Cemento" no es "Cemento blanco").
    if tipo_igual_materiales:
        a, b = set(buscado.tokens), set(cand.tokens)
        corto, largo = (a, b) if len(a) <= len(b) else (b, a)
        if len(corto) >= 2 and corto <= largo:
            valor = max(valor, 0.80)
    return valor


def emparejar_recurso(
    nombre: str, tipo: str, candidatos: Sequence[RecursoRef], umbral: float = 0.70, excluidos: frozenset[int] = frozenset()
) -> Optional[tuple[RecursoRef, float]]:
    """El mejor candidato del mismo tipo, o None si ninguno supera el umbral."""
    buscado = preparar(nombre)
    mejor: Optional[tuple[RecursoRef, float]] = None
    for c in candidatos:
        if c.tipo != tipo or c.clave in excluidos:
            continue
        v = _puntaje_recurso(buscado, preparar(c.nombre), tipo == "material")
        if v is not None and v >= umbral and (mejor is None or v > mejor[1]):
            mejor = (c, v)
    return mejor
