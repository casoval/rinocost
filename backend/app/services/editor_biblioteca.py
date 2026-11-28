"""Editor de bibliotecas: crear bibliotecas desde cero, grupos de ítems, catálogo de recursos y los ítems con sus líneas.

Un ítem guarda SOLO costo directo: materiales, mano de obra y equipo (cantidad por unidad). Cargas sociales, impuestos, gastos
generales y utilidad los calcula el modelo de cálculo de cada usuario.

Al agregar una línea a un ítem se puede elegir un recurso de la biblioteca o ESCRIBIRLO libremente: si no existe, se crea en el
catálogo de recursos de la biblioteca con su unidad (y la unidad se agrega a las unidades de la persona).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Apu, ApuLinea, Biblioteca, GrupoApu, Recurso
from ..importers.b1_parser import normalizar_unidad
from ..matching import LineaApuNueva, costo_unitario
from . import unidades
from .bibliotecas import _nombre_normalizado

TIPOS_RECURSO = ("material", "mano_obra", "equipo")
ORIGENES = ("biblioteca", "medido", "calculado", "similar", "comunitario", "referencial", "manual", "pendiente")


def _texto(valor: Optional[str], campo: str, maximo: int) -> str:
    t = " ".join((valor or "").split())
    if not t:
        raise ValueError(f"Falta {campo}.")
    if len(t) > maximo:
        raise ValueError(f"{campo[0].upper() + campo[1:]} no puede pasar de {maximo} caracteres.")
    return t


def _no_negativo(v, campo: str) -> Optional[Decimal]:
    if v is None or v == "":
        return None
    d = Decimal(str(v))
    if not d.is_finite() or d < 0:
        raise ValueError(f"{campo[0].upper() + campo[1:]} debe ser un número igual o mayor que cero.")
    return d


def _estado(cantidad, precio) -> str:
    return "completo" if cantidad is not None and precio is not None else "pendiente"


def _nn(texto: str) -> str:
    return _nombre_normalizado(texto) or texto.lower()


# ------------------------------------------------------------------ bibliotecas
def crear_biblioteca(db: Session, nombre: str, descripcion: Optional[str] = None) -> Biblioteca:
    b = Biblioteca(nombre=_texto(nombre, "el nombre de la biblioteca", 200), descripcion=(descripcion or "").strip() or None)
    db.add(b)
    db.commit()
    return b


def actualizar_biblioteca(db: Session, b: Biblioteca, nombre: Optional[str], descripcion: Optional[str]) -> Biblioteca:
    if nombre is not None:
        b.nombre = _texto(nombre, "el nombre de la biblioteca", 200)
    if descripcion is not None:
        b.descripcion = descripcion.strip() or None
    db.commit()
    return b


# ------------------------------------------------------------------ grupos
def _ancestros(db: Session, grupo_id: Optional[int]) -> set[int]:
    vistos: set[int] = set()
    while grupo_id is not None and grupo_id not in vistos:
        vistos.add(grupo_id)
        g = db.get(GrupoApu, grupo_id)
        grupo_id = g.padre_id if g else None
    return vistos


def _grupo_de(db: Session, b: Biblioteca, grupo_id: Optional[int]) -> Optional[GrupoApu]:
    if grupo_id is None:
        return None
    g = db.get(GrupoApu, grupo_id)
    if g is None or g.biblioteca_id != b.id:
        raise LookupError("Ese grupo no existe en esta biblioteca.")
    return g


def crear_grupo(db: Session, b: Biblioteca, nombre: str, padre_id: Optional[int] = None) -> GrupoApu:
    _grupo_de(db, b, padre_id)
    orden = (db.scalar(select(func.max(GrupoApu.orden)).where(GrupoApu.biblioteca_id == b.id)) or 0) + 1
    g = GrupoApu(biblioteca_id=b.id, nombre=_texto(nombre, "el nombre del grupo", 200), padre_id=padre_id, orden=orden)
    db.add(g)
    db.commit()
    return g


def actualizar_grupo(db: Session, g: GrupoApu, nombre: Optional[str], padre_id: Optional[int], cambiar_padre: bool, orden: Optional[int]) -> GrupoApu:
    if nombre is not None:
        g.nombre = _texto(nombre, "el nombre del grupo", 200)
    if cambiar_padre:
        b = db.get(Biblioteca, g.biblioteca_id)
        _grupo_de(db, b, padre_id)
        if padre_id is not None and g.id in _ancestros(db, padre_id):
            raise ValueError("Un grupo no puede quedar dentro de sí mismo ni de uno de sus subgrupos.")
        g.padre_id = padre_id
    if orden is not None:
        g.orden = orden
    db.commit()
    return g


def borrar_grupo(db: Session, g: GrupoApu) -> None:
    """Los ítems del grupo quedan «sin grupo» y los subgrupos suben un nivel; no se borra ningún ítem."""
    for a in db.scalars(select(Apu).where(Apu.grupo_id == g.id)).all():
        a.grupo_id = None
    for h in db.scalars(select(GrupoApu).where(GrupoApu.padre_id == g.id)).all():
        h.padre_id = g.padre_id
    db.flush()
    db.delete(g)
    db.commit()


# ------------------------------------------------------------------ recursos
def listar_recursos(db: Session, b: Biblioteca, tipo: Optional[str] = None, q: Optional[str] = None) -> list[tuple[Recurso, int]]:
    usos = dict(db.execute(select(ApuLinea.recurso_id, func.count()).join(Apu, Apu.id == ApuLinea.apu_id)
                           .where(Apu.biblioteca_id == b.id, ApuLinea.recurso_id.is_not(None)).group_by(ApuLinea.recurso_id)).all())
    qn = _nn(q) if q and q.strip() else ""
    out = []
    for r in b.recursos:
        if tipo and r.tipo != tipo:
            continue
        if qn and qn not in r.nombre_normalizado and q.strip().lower() not in r.nombre.lower():
            continue
        out.append((r, int(usos.get(r.id, 0))))
    out.sort(key=lambda t: (t[0].tipo, t[0].nombre.lower()))
    return out


def _buscar_recurso(b: Biblioteca, tipo: str, nombre: str, unidad: str) -> Optional[Recurso]:
    nn, uk = _nn(nombre), normalizar_unidad(unidad)
    for r in b.recursos:
        if r.tipo == tipo and r.nombre_normalizado == nn and normalizar_unidad(r.unidad) == uk:
            return r
    return None


def crear_recurso(db: Session, b: Biblioteca, tipo: str, nombre: str, unidad: str, precio=None) -> Recurso:
    if tipo not in TIPOS_RECURSO:
        raise ValueError("El tipo debe ser material, mano_obra o equipo.")
    nombre = _texto(nombre, "el nombre del recurso", 200)
    unidad = unidades.resolver(db, tipo, _texto(unidad, "la unidad", 20))
    if _buscar_recurso(b, tipo, nombre, unidad) is not None:
        raise ValueError(f"Ya existe «{nombre}» ({unidad}) en esta biblioteca.")
    r = Recurso(biblioteca_id=b.id, tipo=tipo, nombre=nombre, nombre_normalizado=_nn(nombre), unidad=unidad,
                precio_referencia=_no_negativo(precio, "el precio"))
    db.add(r)
    db.commit()
    return r


def actualizar_recurso(db: Session, r: Recurso, nombre: Optional[str] = None, unidad: Optional[str] = None,
                       precio=None, cambiar_precio: bool = False) -> Recurso:
    """Cambia el recurso y lo propaga a las líneas de los ítems de ESTA biblioteca que lo usan (los proyectos ya creados conservan
    su copia). El precio solo se propaga si se envía."""
    b = db.get(Biblioteca, r.biblioteca_id)
    nuevo_nombre = _texto(nombre, "el nombre del recurso", 200) if nombre is not None else r.nombre
    nueva_unidad = unidades.resolver(db, r.tipo, _texto(unidad, "la unidad", 20)) if unidad is not None else r.unidad
    otro = _buscar_recurso(b, r.tipo, nuevo_nombre, nueva_unidad)
    if otro is not None and otro.id != r.id:
        raise ValueError(f"Ya existe «{nuevo_nombre}» ({nueva_unidad}) en esta biblioteca.")
    r.nombre, r.nombre_normalizado, r.unidad = nuevo_nombre, _nn(nuevo_nombre), nueva_unidad
    nuevo_precio = _no_negativo(precio, "el precio") if cambiar_precio else None
    if cambiar_precio:
        r.precio_referencia = nuevo_precio
    for l in db.scalars(select(ApuLinea).join(Apu, Apu.id == ApuLinea.apu_id).where(ApuLinea.recurso_id == r.id, Apu.biblioteca_id == b.id)).all():
        l.descripcion, l.unidad = r.nombre, r.unidad
        if cambiar_precio:
            l.precio_unitario = nuevo_precio
            l.estado = _estado(l.cantidad, l.precio_unitario)
    db.commit()
    return r


def borrar_recurso(db: Session, r: Recurso, forzar: bool = False) -> int:
    """Devuelve cuántas líneas lo usaban. Si lo usan y no se fuerza, no borra (ValueError): las líneas conservan el texto si se fuerza."""
    usos = db.scalar(select(func.count()).select_from(ApuLinea).where(ApuLinea.recurso_id == r.id)) or 0
    if usos and not forzar:
        raise ValueError(f"«{r.nombre}» se usa en {usos} línea(s) de ítems. Quítalo de los ítems o confirma el borrado.")
    for l in db.scalars(select(ApuLinea).where(ApuLinea.recurso_id == r.id)).all():
        l.recurso_id = None
    db.flush()
    db.delete(r)
    db.commit()
    return usos


def buscar_recursos_otras_bibliotecas(db: Session, q: str, tipo: Optional[str], excluir: int, limite: int = 20) -> list[tuple[Recurso, str]]:
    qn = _nn(q) if q and q.strip() else ""
    if not qn:
        return []
    cons = select(Recurso, Biblioteca.nombre).join(Biblioteca, Biblioteca.id == Recurso.biblioteca_id).where(
        Recurso.biblioteca_id != excluir, Recurso.nombre_normalizado.contains(qn))
    if tipo:
        cons = cons.where(Recurso.tipo == tipo)
    return [(r, n) for r, n in db.execute(cons.order_by(Recurso.nombre).limit(limite)).all()]


def copiar_recurso(db: Session, b: Biblioteca, origen_id: int) -> Recurso:
    o = db.get(Recurso, origen_id)
    if o is None:
        raise LookupError("Ese recurso ya no existe.")
    existente = _buscar_recurso(b, o.tipo, o.nombre, o.unidad)
    if existente is not None:
        return existente
    r = Recurso(biblioteca_id=b.id, tipo=o.tipo, nombre=o.nombre, nombre_normalizado=o.nombre_normalizado, unidad=o.unidad,
                precio_referencia=o.precio_referencia)
    db.add(r)
    db.commit()
    return r


# ------------------------------------------------------------------ ítems (APU) y líneas
def _validar_apu_en(db: Session, b: Biblioteca, a: Apu) -> None:
    if a.biblioteca_id != b.id:
        raise LookupError("Ese ítem no está en esta biblioteca.")


def crear_apu(db: Session, b: Biblioteca, nombre: str, unidad: str = "", grupo_id: Optional[int] = None, codigo: Optional[str] = None) -> Apu:
    _grupo_de(db, b, grupo_id)
    nombre = _texto(nombre, "el nombre del ítem", 300)
    unidad = unidades.resolver(db, "item", unidad)
    a = Apu(biblioteca_id=b.id, nombre=nombre, nombre_normalizado=_nn(nombre), unidad=unidad,
            unidad_normalizada=normalizar_unidad(unidad), grupo_id=grupo_id, codigo=(codigo or "").strip()[:40] or None)
    db.add(a)
    db.commit()
    return a


def actualizar_apu(db: Session, a: Apu, nombre: Optional[str] = None, unidad: Optional[str] = None, grupo_id: Optional[int] = None,
                   cambiar_grupo: bool = False, codigo: Optional[str] = None) -> Apu:
    if nombre is not None:
        a.nombre = _texto(nombre, "el nombre del ítem", 300)
        a.nombre_normalizado = _nn(a.nombre)
    if unidad is not None:
        a.unidad = unidades.resolver(db, "item", unidad)
        a.unidad_normalizada = normalizar_unidad(a.unidad)
    if cambiar_grupo:
        _grupo_de(db, db.get(Biblioteca, a.biblioteca_id), grupo_id)
        a.grupo_id = grupo_id
    if codigo is not None:
        a.codigo = codigo.strip()[:40] or None
    db.commit()
    return a


def borrar_apu(db: Session, a: Apu) -> None:
    db.delete(a)
    db.commit()


def duplicar_apu(db: Session, a: Apu) -> Apu:
    copia = Apu(biblioteca_id=a.biblioteca_id, nombre=f"{a.nombre} (copia)"[:300], nombre_normalizado=_nn(f"{a.nombre} copia"),
                unidad=a.unidad, unidad_normalizada=a.unidad_normalizada, grupo_id=a.grupo_id, origen_apu_id=a.id)
    for l in a.lineas:
        copia.lineas.append(ApuLinea(recurso_id=l.recurso_id, tipo=l.tipo, descripcion=l.descripcion, unidad=l.unidad, cantidad=l.cantidad,
                                     precio_unitario=l.precio_unitario, origen_dato="manual", origen_rendimiento=l.origen_rendimiento,
                                     estado=l.estado, fuente=l.fuente))
    db.add(copia)
    db.commit()
    return copia


def costo_directo(a: Apu) -> Optional[Decimal]:
    return costo_unitario([LineaApuNueva(l.tipo, l.descripcion, l.unidad, None if l.cantidad is None else Decimal(l.cantidad),
                                         None if l.precio_unitario is None else Decimal(l.precio_unitario), l.origen_dato,
                                         l.origen_rendimiento, l.requerido_por_pliego, l.estado) for l in a.lineas])[0]


def agregar_linea(db: Session, a: Apu, *, recurso_id: Optional[int] = None, tipo: Optional[str] = None, nombre: Optional[str] = None,
                  unidad: Optional[str] = None, cantidad=None, precio=None, origen_rendimiento: str = "manual") -> tuple[ApuLinea, list[str]]:
    """Agrega una línea. O se elige un recurso de la biblioteca (`recurso_id`) o se escribe uno (`tipo`, `nombre`, `unidad`): si no
    existe, se crea en el catálogo con su unidad. Devuelve la línea y avisos (p. ej. «ya existía con otra unidad»)."""
    b = db.get(Biblioteca, a.biblioteca_id)
    avisos: list[str] = []
    if origen_rendimiento not in ORIGENES:
        raise ValueError(f"Origen del rendimiento inválido: «{origen_rendimiento}».")
    if recurso_id is not None:
        r = db.get(Recurso, recurso_id)
        if r is None or r.biblioteca_id != b.id:
            raise LookupError("Ese recurso no está en esta biblioteca (cópialo primero).")
    else:
        if tipo not in TIPOS_RECURSO:
            raise ValueError("El tipo debe ser material, mano_obra o equipo.")
        nombre = _texto(nombre, "el nombre del recurso", 200)
        unidad = unidades.resolver(db, tipo, _texto(unidad, "la unidad", 20))
        r = _buscar_recurso(b, tipo, nombre, unidad)
        if r is None:
            parecido = next((x for x in b.recursos if x.tipo == tipo and x.nombre_normalizado == _nn(nombre)), None)
            r = Recurso(biblioteca_id=b.id, tipo=tipo, nombre=nombre, nombre_normalizado=_nn(nombre), unidad=unidad,
                        precio_referencia=_no_negativo(precio, "el precio"))
            db.add(r)
            db.flush()
            avisos.append(f"Se agregó «{nombre}» ({unidad}) a tus {'materiales' if tipo == 'material' else 'mano de obra' if tipo == 'mano_obra' else 'equipos'}.")
            if parecido is not None:
                avisos.append(f"Ya tenías «{parecido.nombre}» con otra unidad ({parecido.unidad}); se creó uno aparte con {unidad}.")
    cant = _no_negativo(cantidad, "la cantidad")
    prec = _no_negativo(precio, "el precio")
    if prec is None and r.precio_referencia is not None:
        prec = Decimal(r.precio_referencia)
    l = ApuLinea(apu_id=a.id, recurso_id=r.id, tipo=r.tipo, descripcion=r.nombre, unidad=r.unidad, cantidad=cant, precio_unitario=prec,
                 origen_dato="manual", origen_rendimiento=origen_rendimiento, estado=_estado(cant, prec))
    a.lineas.append(l)
    db.commit()
    return l, avisos


def actualizar_linea(db: Session, l: ApuLinea, cantidad=None, precio=None, origen_rendimiento: Optional[str] = None,
                     cambiar_cantidad: bool = False, cambiar_precio: bool = False) -> ApuLinea:
    if cambiar_cantidad:
        l.cantidad = _no_negativo(cantidad, "la cantidad")
    if cambiar_precio:
        l.precio_unitario = _no_negativo(precio, "el precio")
    if origen_rendimiento is not None:
        if origen_rendimiento not in ORIGENES:
            raise ValueError(f"Origen del rendimiento inválido: «{origen_rendimiento}».")
        l.origen_rendimiento = origen_rendimiento
    l.estado = _estado(l.cantidad, l.precio_unitario)
    db.commit()
    return l


def borrar_linea(db: Session, l: ApuLinea) -> None:
    db.delete(l)
    db.commit()
