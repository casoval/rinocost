"""Lógica constructiva: en qué ETAPA de la obra cae cada ítem y qué ítems deben terminar antes de que empiece.

Orden habitual de una obra de refacción o construcción:
    demolición y preliminares → obra gruesa → instalaciones → revoques, cielos y pisos → carpintería → pintura
    → artefactos y accesorios → limpieza y entrega.

La etapa se deduce del NOMBRE del ítem (palabras clave). Un ítem sin ninguna palabra clave hereda la etapa del ítem
anterior de la lista. Cada ítem tiene como predecesoras a TODOS los ítems de la etapa anterior que tenga ítems; los de una
misma etapa pueden hacerse a la vez. Es una propuesta: el usuario puede cambiar las predecesoras de cualquier ítem.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Sequence

from .motor import Actividad

FASES = (
    "Demolición y preliminares",
    "Obra gruesa",
    "Instalaciones",
    "Revoques, cielos y pisos",
    "Carpintería",
    "Pintura",
    "Artefactos y accesorios",
    "Limpieza y entrega",
)
_GRUESA = 1
_ACABADOS = 6  # etapa de los acabados finales (artefactos y accesorios)

# Acabados que dependen SOLO de otro ítem y se hacen al final: (palabras del ítem, palabras del ítem del que depende).
# Ej.: instalar la cajonería es colocar puertas o la estructura de madera sobre el mesón ya terminado.
_SOLO_DE = (
    (("cajoneria", "gabinete", "mueble bajo", "mueble alto"), ("meson", "mesada")),
)

# (etapa, palabras clave). Se prueba en este orden: el primer grupo que coincide gana. Por eso «retiro de cielo raso»
# cae en demolición (retiro) y no en cielos, y «instalación de artefactos» en artefactos y no en instalaciones.
_REGLAS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (0, ("retiro", "demol", "desmont", "desarm", "picado", "remocion", "extraccion", "desinstal", "escombro", "faena",
         "replanteo", "trazado", "desbroce", "campamento", "cerco provisional", "letrero", "obras preliminares")),
    (7, ("limpieza", "entrega", "aseo")),
    (6, ("artefacto", "lavamanos", "inodoro", "lavaplato", "lavadero", "griferia", "luminaria", "lampara", "interruptor",
         "tomacorriente", "espejo", "accesorio", "ducha", "bide", "urinario", "toallero", "jabonera", "campana", "extractor")),
    (5, ("pintura", "pintado", "latex", "barniz", "laca", "sellador", "empaste", "esmalte")),
    (4, ("puerta", "ventana", "carpinteria", "marco", "baranda", "reja", "vidrio", "cerradura", "chapa", "aluminio",
         "metalica", "closet", "mueble", "cajoneria", "gabinete")),
    (3, ("revoque", "enlucido", "revestimiento", "estuco", "yeso", "cielo raso", "cielo falso", "tumbado", "piso",
         "ceramica", "porcelanato", "zocalo", "azulejo", "carpeta", "alfombra", "parquet", "pared falsa", "tabique")),
    (2, ("instalacion", "electric", "sanitari", "agua potable", "caneria", "tuberia", "desague", "cableado", "tablero",
         "canaleta", "bajante", "punto de", "red de", "inst.")),
    (1, ("excav", "cimien", "zapata", "hormigon", "muro", "mamposteria", "ladrillo", "columna", "viga", "losa",
         "estructura", "relleno", "sobrecimiento", "cubierta", "techo", "cercha", "impermeabil", "acero", "encofrado",
         "bloque", "cerramiento", "obra gruesa")),
)


def _normal(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def _coincide(texto: str, claves: Sequence[str]) -> bool:
    return any(re.search(r"(?<![a-z])" + re.escape(c), texto) for c in claves)


def fase_por_nombre(nombre: str) -> int | None:
    """Etapa (0..7) según las palabras clave del nombre; None si no reconoce ninguna."""
    t = _normal(nombre)
    for fase, claves in _REGLAS:
        if _coincide(t, claves):
            return fase
    return None


def _anclas(actividades: Sequence[Actividad]) -> dict[int, list[int]]:
    """{id del acabado: ids de los ítems de los que depende SOLO}; solo si esos ítems existen en el proyecto."""
    out: dict[int, list[int]] = {}
    for propios, de in _SOLO_DE:
        esta = [a for a in actividades if _coincide(_normal(a.nombre), propios)]
        ancla = [a.id for a in actividades if _coincide(_normal(a.nombre), de) and a not in esta]
        if ancla:
            out.update({a.id: list(ancla) for a in esta})
    return out


def asignar_fases(actividades_en_orden: Sequence[Actividad]) -> dict[int, int]:
    """{id de actividad: etapa}. Orden de criterios: nombre del ítem, luego nombre del módulo y, si ninguno dice nada, la
    etapa del ítem anterior (el primero: obra gruesa). Los acabados que dependen solo de otro ítem van a la etapa final."""
    anclas = _anclas(actividades_en_orden)
    out: dict[int, int] = {}
    previa = _GRUESA
    for a in actividades_en_orden:
        f = fase_por_nombre(a.nombre)
        if f is None:
            f = fase_por_nombre(a.grupo)
        previa = out[a.id] = previa if f is None else f
        if a.id in anclas:
            out[a.id] = _ACABADOS  # no arrastra la herencia: «previa» sigue siendo la del ítem anterior
    return out


def predecesoras_constructivas(actividades_en_orden: Sequence[Actividad]) -> dict[int, list[int]]:
    """{id: ids de sus predecesoras}: todos los ítems de la etapa anterior que tenga ítems; la primera etapa no tiene.
    Excepción: un acabado que depende solo de otro ítem (cajonería → mesón) espera únicamente a ese."""
    fases = asignar_fases(actividades_en_orden)
    anclas = _anclas(actividades_en_orden)
    por_fase: dict[int, list[int]] = {}
    for a in actividades_en_orden:
        por_fase.setdefault(fases[a.id], []).append(a.id)
    orden = sorted(por_fase)
    anterior = {f: (por_fase[orden[i - 1]] if i else []) for i, f in enumerate(orden)}
    return {a.id: (list(anclas[a.id]) if a.id in anclas else list(anterior[fases[a.id]])) for a in actividades_en_orden}
