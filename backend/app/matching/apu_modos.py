"""Arma las líneas de un APU según el modo de recursos elegido.

- pliego:     los recursos que pide la especificación (cantidades pendientes; si la biblioteca tiene el
              mismo recurso, se toma su cantidad y precio).
- biblioteca: el APU del usuario tal cual; se avisa de lo que el pliego pide y el APU no incluye.
- hibrido:    el APU del usuario + lo que el pliego pide y falta (pendiente).
Nunca se inventa un rendimiento: lo que no tiene fuente queda 'pendiente'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence

from .motor import RecursoRef, emparejar_recurso

MODOS = ("pliego", "biblioteca", "hibrido")


@dataclass
class RequisitoRef:
    tipo: str
    nombre: str
    unidad: Optional[str]
    pagina: int
    detalle: Optional[str] = None


@dataclass
class LineaBib:
    tipo: str
    descripcion: str
    unidad: str
    cantidad: Optional[Decimal]
    precio_unitario: Optional[Decimal]
    origen_rendimiento: str = "biblioteca"
    recurso_id: Optional[int] = None


@dataclass
class LineaApuNueva:
    tipo: str
    descripcion: str
    unidad: str
    cantidad: Optional[Decimal]
    precio_unitario: Optional[Decimal]
    origen_dato: str  # pliego | biblioteca | ambos | manual
    origen_rendimiento: str  # biblioteca | pendiente | ...
    requerido_por_pliego: bool
    estado: str  # completo | pendiente
    fuente: Optional[str] = None
    recurso_id: Optional[int] = None


@dataclass
class ResultadoModo:
    modo: str
    lineas: list[LineaApuNueva] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _estado(cantidad: Optional[Decimal], precio: Optional[Decimal]) -> str:
    return "completo" if cantidad is not None and precio is not None else "pendiente"


def costo_unitario(lineas: Sequence[LineaApuNueva]) -> tuple[Optional[Decimal], int]:
    """(costo, pendientes). El costo solo se da si TODAS las líneas están completas."""
    pendientes = sum(1 for l in lineas if l.cantidad is None or l.precio_unitario is None)
    if not lineas or pendientes:
        return None, pendientes
    total = sum((l.cantidad * l.precio_unitario for l in lineas), Decimal("0"))  # type: ignore[operator]
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), 0


def _linea_de_requisito(r: RequisitoRef, bib: Optional[LineaBib]) -> LineaApuNueva:
    return LineaApuNueva(
        tipo=r.tipo, descripcion=r.nombre, unidad=(bib.unidad if bib else None) or r.unidad or "",
        cantidad=bib.cantidad if bib else None, precio_unitario=bib.precio_unitario if bib else None,
        origen_dato="pliego", origen_rendimiento=(bib.origen_rendimiento if bib else "pendiente"),
        requerido_por_pliego=True, estado=_estado(bib.cantidad if bib else None, bib.precio_unitario if bib else None),
        fuente=f"Especificaciones, p. {r.pagina}", recurso_id=bib.recurso_id if bib else None,
    )


def _linea_de_biblioteca(b: LineaBib, requerida: bool, fuente: Optional[str]) -> LineaApuNueva:
    return LineaApuNueva(
        tipo=b.tipo, descripcion=b.descripcion, unidad=b.unidad, cantidad=b.cantidad, precio_unitario=b.precio_unitario,
        origen_dato="ambos" if requerida else "biblioteca", origen_rendimiento=b.origen_rendimiento,
        requerido_por_pliego=requerida, estado=_estado(b.cantidad, b.precio_unitario), fuente=fuente,
        recurso_id=b.recurso_id,
    )


def armar_lineas(
    modo: str,
    requisitos: Sequence[RequisitoRef],
    lineas_biblioteca: Optional[Sequence[LineaBib]],
    tomar_de_biblioteca: bool = True,
) -> ResultadoModo:
    if modo not in MODOS:
        raise ValueError(f"Modo de recursos no válido: {modo!r}. Usa uno de {MODOS}.")
    res = ResultadoModo(modo=modo)
    bib = list(lineas_biblioteca or [])

    # Emparejar cada requisito del pliego con a lo sumo una línea de la biblioteca.
    refs = [RecursoRef(i, l.tipo, l.descripcion) for i, l in enumerate(bib)]
    usadas: set[int] = set()
    pareja: dict[int, int] = {}
    for idx, r in enumerate(requisitos):
        m = emparejar_recurso(r.nombre, r.tipo, refs, excluidos=frozenset(usadas))
        if m:
            pareja[idx] = m[0].clave
            usadas.add(m[0].clave)

    sin_apu = lineas_biblioteca is None
    if sin_apu and modo != "pliego":
        res.avisos.append("No hay APU en la biblioteca para este ítem: se usaron los recursos del pliego.")
        modo_efectivo = "pliego"
    else:
        modo_efectivo = modo
    if not requisitos and modo_efectivo == "pliego":
        res.avisos.append("La especificación no lista recursos para este ítem: el APU queda vacío.")

    if modo_efectivo == "pliego":
        for idx, r in enumerate(requisitos):
            origen = bib[pareja[idx]] if (idx in pareja and tomar_de_biblioteca) else None
            res.lineas.append(_linea_de_requisito(r, origen))
        return res

    pliego_de = {pareja[i]: requisitos[i] for i in pareja}
    for j, b in enumerate(bib):
        r = pliego_de.get(j)
        res.lineas.append(_linea_de_biblioteca(b, r is not None, f"Especificaciones, p. {r.pagina}" if r else None))

    faltantes = [r for i, r in enumerate(requisitos) if i not in pareja]
    for r in faltantes:
        if modo_efectivo == "hibrido":
            res.lineas.append(_linea_de_requisito(r, None))
        else:  # biblioteca: solo se informa, no se agrega nada
            res.avisos.append(
                f"El pliego pide {_rotulo(r.tipo)} '{r.nombre}' (p. {r.pagina}) y el APU de tu biblioteca no lo incluye."
            )
    return res


def _rotulo(tipo: str) -> str:
    return {"material": "el material", "mano_obra": "la mano de obra", "equipo": "el equipo"}.get(tipo, tipo)
