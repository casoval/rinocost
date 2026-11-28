"""Unidades de medida: predefinidas por tipo de recurso + las que agrega la persona (puede escribir cualquiera).

El catálogo se ofrece al elegir (material: Kg, Pza, Glb, Rollo, m…; mano de obra y equipo: Hr, Día…; ítem: m2, m3, Pza…), pero
nunca limita: lo que se escribe y no existe se agrega a «mis unidades» de ese tipo. Para que «kg», «KG» y «Kg» sean la misma
unidad se compara con la clave normalizada; al ESCRIBIR en el editor se usa el símbolo del catálogo. Al IMPORTAR no se cambia
ningún texto: solo se registran las unidades nuevas.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Unidad
from ..importers.b1_parser import normalizar_unidad

TIPOS = ("material", "mano_obra", "equipo", "item")

PREDEFINIDAS: dict[str, list[tuple[str, str]]] = {
    "material": [("Kg", "Kilogramo"), ("Pza", "Pieza"), ("Glb", "Global"), ("Rollo", "Rollo"), ("m", "Metro"), ("m2", "Metro cuadrado"),
                 ("m3", "Metro cúbico"), ("L", "Litro"), ("Gal", "Galón"), ("Bolsa", "Bolsa"), ("Saco", "Saco"), ("Hoja", "Hoja"),
                 ("Tubo", "Tubo"), ("Barra", "Barra"), ("Plancha", "Plancha"), ("Caja", "Caja"), ("Juego", "Juego"), ("Par", "Par"),
                 ("P2", "Pie cuadrado"), ("Tn", "Tonelada"), ("Lata", "Lata")],
    "mano_obra": [("Hr", "Hora"), ("Día", "Día"), ("Jornal", "Jornal"), ("Mes", "Mes"), ("Glb", "Global")],
    "equipo": [("Hr", "Hora"), ("Día", "Día"), ("Mes", "Mes"), ("Glb", "Global"), ("Viaje", "Viaje")],
    "item": [("m", "Metro"), ("m2", "Metro cuadrado"), ("m3", "Metro cúbico"), ("Pza", "Pieza"), ("Glb", "Global"), ("Kg", "Kilogramo"),
             ("L", "Litro"), ("Pto", "Punto"), ("Tn", "Tonelada")],
}


def clave(texto: str) -> str:
    return normalizar_unidad(texto)


def _validar(tipo: str, simbolo: str) -> str:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de unidad inválido: «{tipo}».")
    simbolo = (simbolo or "").strip()
    if not simbolo:
        raise ValueError("Escribe la unidad.")
    if len(simbolo) > 20:
        raise ValueError("La unidad no puede pasar de 20 caracteres.")
    return simbolo


def sembrar(db: Session) -> int:
    """Agrega las unidades predefinidas que falten (se puede llamar siempre). Devuelve cuántas agregó."""
    existentes = {(u.tipo, u.clave) for u in db.scalars(select(Unidad)).all()}
    n = 0
    for tipo, lista in PREDEFINIDAS.items():
        for orden, (simbolo, nombre) in enumerate(lista):
            k = clave(simbolo)
            if (tipo, k) not in existentes:
                db.add(Unidad(tipo=tipo, simbolo=simbolo, clave=k, nombre=nombre, predefinida=True, orden=orden))
                existentes.add((tipo, k))
                n += 1
    if n:
        db.commit()
    return n


def listar(db: Session, tipo: Optional[str] = None) -> list[Unidad]:
    q = select(Unidad).order_by(Unidad.predefinida.desc(), Unidad.orden, Unidad.simbolo)
    if tipo:
        q = q.where(Unidad.tipo == tipo)
    return list(db.scalars(q).all())


def _buscar(db: Session, tipo: str, simbolo: str) -> Optional[Unidad]:
    return db.scalar(select(Unidad).where(Unidad.tipo == tipo, Unidad.clave == clave(simbolo)))


def resolver(db: Session, tipo: str, texto: str) -> str:
    """Símbolo a usar para lo que escribió la persona: el del catálogo si ya existe (kg → Kg); si no, el texto tal cual, que se
    agrega a sus unidades. Vacío se queda vacío."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    texto = _validar(tipo, texto)
    u = _buscar(db, tipo, texto)
    if u is not None:
        return u.simbolo
    db.add(Unidad(tipo=tipo, simbolo=texto, clave=clave(texto), predefinida=False, orden=1000))
    db.flush()
    return texto


def registrar(db: Session, tipo: str, texto: str) -> None:
    """Para importaciones: agrega la unidad al catálogo si falta, sin cambiar el texto importado."""
    texto = (texto or "").strip()
    if texto and len(texto) <= 20 and _buscar(db, tipo, texto) is None:
        db.add(Unidad(tipo=tipo, simbolo=texto, clave=clave(texto), predefinida=False, orden=1000))
        db.flush()


def agregar(db: Session, tipo: str, simbolo: str, nombre: Optional[str] = None) -> Unidad:
    simbolo = _validar(tipo, simbolo)
    if _buscar(db, tipo, simbolo) is not None:
        raise ValueError(f"La unidad «{simbolo}» ya existe en {tipo}.")
    u = Unidad(tipo=tipo, simbolo=simbolo, clave=clave(simbolo), nombre=(nombre or "").strip() or None, predefinida=False, orden=1000)
    db.add(u)
    db.commit()
    return u


def borrar(db: Session, unidad_id: int) -> None:
    u = db.get(Unidad, unidad_id)
    if u is None:
        raise LookupError("Esa unidad ya no existe.")
    if u.predefinida:
        raise ValueError("Las unidades predefinidas no se pueden borrar (solo las que agregaste).")
    db.delete(u)
    db.commit()
