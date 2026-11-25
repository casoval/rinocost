"""Bibliotecas de APU: importación desde Excel y consulta."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Apu, ApuLinea, Biblioteca, Recurso
from ..importers.biblioteca_excel import ResultadoBiblioteca
from ..matching import LineaApuNueva, costo_unitario, preparar
from ..schemas import ApuResumenOut, BibliotecaOut


def _nombre_normalizado(texto: str) -> str:
    return " ".join(preparar(texto).tokens)


def crear_desde_excel(db: Session, nombre: str, resultado: ResultadoBiblioteca) -> Biblioteca:
    """Crea la biblioteca con sus APU y un catálogo de recursos sin duplicados (por tipo y nombre normalizado)."""
    bib = Biblioteca(nombre=nombre)
    catalogo: dict[tuple[str, str], Recurso] = {}
    for a in resultado.apus:
        apu = Apu(
            codigo=a.codigo, nombre=a.nombre, nombre_normalizado=_nombre_normalizado(a.nombre),
            unidad=a.unidad, unidad_normalizada=a.unidad_normalizada,
        )
        for l in a.lineas:
            clave = (l.tipo, _nombre_normalizado(l.recurso) or l.recurso.lower())
            recurso = catalogo.get(clave)
            if recurso is None:
                recurso = Recurso(tipo=l.tipo, nombre=l.recurso, nombre_normalizado=clave[1], unidad=l.unidad)
                catalogo[clave] = recurso
                bib.recursos.append(recurso)
            apu.lineas.append(ApuLinea(
                tipo=l.tipo, descripcion=l.recurso, unidad=l.unidad, cantidad=l.cantidad,
                precio_unitario=l.precio_unitario, origen_dato="biblioteca", origen_rendimiento=l.origen_rendimiento,
                estado="completo" if l.cantidad is not None and l.precio_unitario is not None else "pendiente",
                recurso=recurso,
            ))
        bib.apus.append(apu)
    db.add(bib)
    db.commit()
    db.refresh(bib)
    return bib


def costo_apu(apu: Apu) -> Optional[Decimal]:
    lineas = [
        LineaApuNueva(l.tipo, l.descripcion, l.unidad, None if l.cantidad is None else Decimal(l.cantidad),
                      None if l.precio_unitario is None else Decimal(l.precio_unitario),
                      l.origen_dato, l.origen_rendimiento, l.requerido_por_pliego, l.estado)
        for l in apu.lineas
    ]
    return costo_unitario(lineas)[0]


def a_biblioteca_out(b: Biblioteca) -> BibliotecaOut:
    return BibliotecaOut(id=b.id, nombre=b.nombre, total_apus=len(b.apus), total_lineas=sum(len(a.lineas) for a in b.apus))


def listar(db: Session) -> list[BibliotecaOut]:
    return [a_biblioteca_out(b) for b in db.scalars(select(Biblioteca).order_by(Biblioteca.id.desc())).all()]


def listar_apus(db: Session, biblioteca: Biblioteca) -> list[ApuResumenOut]:
    out = []
    for a in biblioteca.apus:
        costo = costo_apu(a)
        out.append(ApuResumenOut(id=a.id, nombre=a.nombre, unidad=a.unidad, codigo=a.codigo, lineas=len(a.lineas),
                                 costo=None if costo is None else f"{costo:.2f}"))
    return out
