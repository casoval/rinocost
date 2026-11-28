"""Modelo de costos configurable: de los recursos del APU (materiales, mano de obra, equipo) al precio unitario.

Un modelo es una lista ORDENADA de secciones; cada sección puede sumar los recursos de un tipo ("directo") y tener
pasos (cargas sociales, herramientas, gastos generales, utilidad, impuestos...). Cada paso es un porcentaje sobre
una BASE: la lista de referencias a valores ya calculados antes. Eso permite reproducir el B-2 boliviano y
también un modelo privado propio, sin escribir código.

Referencias válidas en `base`:
    "<seccion>"           total de esa sección (directo + sus pasos)
    "<seccion>.directo"   solo los recursos de la sección (sin pasos)
    "<paso>"              valor de un paso anterior
Solo se pueden citar valores anteriores: así no hay referencias circulares.

El modelo es un dato (JSON), no código: se guarda por proyecto y se puede copiar, editar y compartir.
Todo con Decimal: nada de redondeos escondidos. Solo se redondea el precio final (decimales configurables).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

TIPOS_RECURSO = ("material", "mano_obra", "equipo")
_CERO = Decimal("0")
MAX_PORCENTAJE = Decimal("1000")
MAX_SECCIONES, MAX_PASOS, MAX_TEXTO = 30, 60, 400


def _d(v) -> Decimal:
    if v is None or v == "":
        return _CERO
    return v if isinstance(v, Decimal) else Decimal(str(v).replace(",", "."))


def _porcentaje(valor, codigo: str) -> Decimal:
    """Porcentaje escrito por la persona: obligatorio, número finito. Nada de '' → 0 en silencio."""
    texto = str(valor).strip().replace(",", ".") if valor is not None else ""
    if texto == "":
        raise ValueError(f"Paso '{codigo}': falta el porcentaje.")
    try:
        d = Decimal(texto)
    except ArithmeticError:
        raise ValueError(f"Paso '{codigo}': «{valor}» no es un número.") from None
    if not d.is_finite():
        raise ValueError(f"Paso '{codigo}': «{valor}» no es un número válido.")
    return d


@dataclass
class Paso:
    codigo: str
    etiqueta: str                  # texto del B-2; admite {pct}, p. ej. "CARGAS SOCIALES = {pct}% DEL SUBTOTAL DE M.O."
    porcentaje: Decimal            # 55 significa 55 %
    base: list[str]
    activo: bool = True
    minimo: Optional[Decimal] = None   # rango de referencia (solo informativo: la app avisa, no bloquea)
    maximo: Optional[Decimal] = None
    ayuda: str = ""                    # de dónde sale / qué base usa, en una línea

    def a_dict(self) -> dict:
        d = {"codigo": self.codigo, "etiqueta": self.etiqueta, "porcentaje": str(self.porcentaje),
             "base": list(self.base), "activo": self.activo}
        if self.minimo is not None:
            d["minimo"] = str(self.minimo)
        if self.maximo is not None:
            d["maximo"] = str(self.maximo)
        if self.ayuda:
            d["ayuda"] = self.ayuda
        return d


@dataclass
class Seccion:
    codigo: str
    titulo: str
    tipo_recurso: Optional[str] = None     # material | mano_obra | equipo | None (solo pasos)
    pasos: list[Paso] = field(default_factory=list)
    activo: bool = True
    etiqueta_total: Optional[str] = None   # "TOTAL MANO DE OBRA"

    def a_dict(self) -> dict:
        return {"codigo": self.codigo, "titulo": self.titulo, "tipo_recurso": self.tipo_recurso, "activo": self.activo,
                "etiqueta_total": self.etiqueta_total, "pasos": [p.a_dict() for p in self.pasos]}


@dataclass
class ModeloCostos:
    codigo: str
    nombre: str
    descripcion: str = ""
    secciones: list[Seccion] = field(default_factory=list)
    decimales: int = 2
    nota: str = ""                 # aclaración visible (p. ej. de dónde salen los porcentajes)

    def a_dict(self) -> dict:
        return {"codigo": self.codigo, "nombre": self.nombre, "descripcion": self.descripcion,
                "decimales": self.decimales, "nota": self.nota, "secciones": [s.a_dict() for s in self.secciones]}

    @classmethod
    def desde_dict(cls, d: dict) -> "ModeloCostos":
        secciones = [
            Seccion(codigo=s["codigo"], titulo=s["titulo"], tipo_recurso=s.get("tipo_recurso"),
                    activo=s.get("activo", True), etiqueta_total=s.get("etiqueta_total"),
                    pasos=[Paso(p["codigo"], p["etiqueta"], _porcentaje(p["porcentaje"], p["codigo"]), list(p["base"]),
                           p.get("activo", True),
                           _porcentaje(p["minimo"], p["codigo"]) if p.get("minimo") not in (None, "") else None,
                           _porcentaje(p["maximo"], p["codigo"]) if p.get("maximo") not in (None, "") else None,
                           p.get("ayuda", ""))
                           for p in s.get("pasos", [])])
            for s in d.get("secciones", [])
        ]
        return cls(d["codigo"], d["nombre"], d.get("descripcion", ""), secciones, int(d.get("decimales", 2)),
                   d.get("nota", ""))

    def copia(self, codigo: Optional[str] = None, nombre: Optional[str] = None) -> "ModeloCostos":
        m = ModeloCostos.desde_dict(self.a_dict())
        m.codigo, m.nombre = codigo or self.codigo, nombre or self.nombre
        return m

    def paso(self, codigo: str) -> Paso:
        for s in self.secciones:
            for p in s.pasos:
                if p.codigo == codigo:
                    return p
        raise KeyError(f"No existe el paso '{codigo}' en el modelo.")


def validar_modelo(m: ModeloCostos) -> list[str]:
    """Devuelve la lista de problemas (vacía si el modelo es válido)."""
    errores: list[str] = []
    vistos: set[str] = set()
    valores: set[str] = set()
    tipos_usados: set[str] = set()
    if not m.secciones:
        errores.append("El modelo no tiene secciones.")
    if not 0 <= m.decimales <= 6:
        errores.append("Los decimales deben estar entre 0 y 6.")
    if len(m.secciones) > MAX_SECCIONES or sum(len(s.pasos) for s in m.secciones) > MAX_PASOS:
        errores.append(f"El modelo es demasiado grande (máximo {MAX_SECCIONES} secciones y {MAX_PASOS} pasos).")
    for texto in (m.codigo, m.nombre, m.descripcion, m.nota, *(s.titulo for s in m.secciones),
                  *(p.etiqueta for s in m.secciones for p in s.pasos), *(p.ayuda for s in m.secciones for p in s.pasos)):
        if len(texto or "") > MAX_TEXTO:
            errores.append(f"Hay un texto de más de {MAX_TEXTO} caracteres.")
            break
    for s in m.secciones:
        if s.codigo in vistos:
            errores.append(f"Código repetido: '{s.codigo}'.")
        vistos.add(s.codigo)
        if s.tipo_recurso is not None:
            if s.tipo_recurso not in TIPOS_RECURSO:
                errores.append(f"Sección '{s.codigo}': tipo de recurso inválido '{s.tipo_recurso}'.")
            elif s.tipo_recurso in tipos_usados:
                errores.append(f"Dos secciones suman recursos de tipo '{s.tipo_recurso}': se contarían doble.")
            tipos_usados.add(s.tipo_recurso)
        valores.add(f"{s.codigo}.directo")
        for p in s.pasos:
            if p.codigo in vistos:
                errores.append(f"Código repetido: '{p.codigo}'.")
            vistos.add(p.codigo)
            if not p.porcentaje.is_finite():
                errores.append(f"Paso '{p.codigo}': el porcentaje no es un número válido.")
            elif p.porcentaje < 0:
                errores.append(f"Paso '{p.codigo}': el porcentaje no puede ser negativo.")
            elif p.porcentaje > MAX_PORCENTAJE:
                errores.append(f"Paso '{p.codigo}': el porcentaje no puede pasar de {MAX_PORCENTAJE} %.")
            if not p.base:
                errores.append(f"Paso '{p.codigo}': no tiene base de cálculo.")
            for ref in p.base:
                if ref not in valores:
                    errores.append(f"Paso '{p.codigo}': la base '{ref}' no existe todavía "
                                   f"(solo se pueden citar valores anteriores).")
            valores.add(p.codigo)
        valores.add(s.codigo)
    return errores


@dataclass
class LineaCalculada:
    codigo: str
    etiqueta: str
    porcentaje: Optional[Decimal]
    base: Optional[Decimal]
    valor: Decimal
    seccion: str
    activo: bool = True


@dataclass
class ResultadoCostos:
    directos: dict[str, Decimal]               # por tipo de recurso
    secciones: dict[str, Decimal]              # total de cada sección
    lineas: list[LineaCalculada]
    total: Decimal                             # sin redondear
    precio: Decimal                            # redondeado según el modelo

    def a_dict(self) -> dict:
        return {
            "directos": {k: str(v) for k, v in self.directos.items()},
            "secciones": {k: str(v) for k, v in self.secciones.items()},
            "lineas": [{"codigo": l.codigo, "etiqueta": l.etiqueta, "porcentaje": None if l.porcentaje is None else str(l.porcentaje),
                        "base": None if l.base is None else str(l.base), "valor": str(l.valor), "seccion": l.seccion}
                       for l in self.lineas],
            "total": str(self.total), "precio": str(self.precio),
        }


def _porc_texto(p: Decimal) -> str:
    return f"{p.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}".replace(".", ",")


def calcular(modelo: ModeloCostos, materiales=0, mano_obra=0, equipo=0) -> ResultadoCostos:
    """Calcula el precio unitario a partir de los costos directos por tipo de recurso."""
    errores = validar_modelo(modelo)
    if errores:
        raise ValueError("Modelo de costos inválido: " + " | ".join(errores))
    directos = {"material": _d(materiales), "mano_obra": _d(mano_obra), "equipo": _d(equipo)}
    valores: dict[str, Decimal] = {}
    lineas: list[LineaCalculada] = []
    secciones: dict[str, Decimal] = {}

    for s in modelo.secciones:
        if not s.activo:
            valores[f"{s.codigo}.directo"] = valores[s.codigo] = _CERO
            for p in s.pasos:
                valores[p.codigo] = _CERO
            secciones[s.codigo] = _CERO
            continue
        directo = directos[s.tipo_recurso] if s.tipo_recurso else _CERO
        valores[f"{s.codigo}.directo"] = directo
        suma = directo
        lineas.append(LineaCalculada(f"{s.codigo}.directo", f"SUBTOTAL {s.titulo}", None, None, directo, s.codigo))
        # el total de la sección aún no existe mientras se calculan sus pasos: se completa al final
        for p in s.pasos:
            if not p.activo:
                valores[p.codigo] = _CERO
                continue
            base = sum((valores[r] if r != s.codigo else suma for r in p.base), _CERO)
            valor = base * p.porcentaje / Decimal(100)
            valores[p.codigo] = valor
            suma += valor
            lineas.append(LineaCalculada(p.codigo, p.etiqueta.replace("{pct}", _porc_texto(p.porcentaje)),
                                         p.porcentaje, base, valor, s.codigo))
        valores[s.codigo] = suma
        secciones[s.codigo] = suma

    total = sum(secciones.values(), _CERO)
    cuanto = Decimal(1).scaleb(-modelo.decimales)
    return ResultadoCostos(directos, secciones, lineas, total, total.quantize(cuanto, rounding=ROUND_HALF_UP))
