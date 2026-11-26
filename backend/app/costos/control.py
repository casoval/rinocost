"""Control de la propuesta frente al Precio Referencial (D.S. 0181, NB-SABS, art. 21).

Cada porcentaje cita su fuente y es configurable, porque la norma puede modificarse y el DBC puede exigir otros.
No calcula la garantía de seriedad ni sustituye lo que diga el DBC de la convocatoria.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

_C = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_C, rounding=ROUND_HALF_UP)


@dataclass
class ControlPropuesta:
    precio_referencial: Decimal
    total_propuesta: Decimal
    porcentaje_del_referencial: Decimal
    diferencia: Decimal                       # + = excede el referencial
    excede_referencial: bool
    umbral_85: Decimal
    garantia_adicional: Decimal               # art. 21 I c): solo si propuesta < 85 % del PR
    garantia_cumplimiento: Decimal            # art. 21 I b): 7 % (o 3,5 % para micro y pequeñas empresas)
    garantia_seriedad: Decimal                # art. 21 I a): 1 % del PR
    estado: str
    avisos: list[str]


def controlar_propuesta(
    precio_referencial, total_propuesta, *, pct_cumplimiento="7", pct_seriedad="1", pct_minimo="85",
    micro_pequena_empresa: bool = False, monto_maximo_mype: Optional[str] = "1000000",
) -> ControlPropuesta:
    pr, tp = Decimal(str(precio_referencial)), Decimal(str(total_propuesta))
    if pr <= 0:
        raise ValueError("El precio referencial debe ser mayor que cero.")
    pc = Decimal(str(pct_cumplimiento))
    avisos: list[str] = []
    if micro_pequena_empresa:
        tope = Decimal(str(monto_maximo_mype)) if monto_maximo_mype else None
        if tope is not None and tp <= tope:
            pc = Decimal("3.5")
            avisos.append("Micro y pequeña empresa en contratación hasta Bs 1.000.000: garantía de cumplimiento 3,5 % "
                          "(o retención del 3,5 % de cada pago). Verifica lo que exija el DBC.")
        else:
            avisos.append("El 3,5 % para micro y pequeñas empresas aplica solo hasta Bs 1.000.000; se usa el porcentaje general.")
    minimo = pr * Decimal(str(pct_minimo)) / 100
    excede = tp > pr
    adicional = minimo - tp if tp < minimo else Decimal(0)
    if excede:
        estado = "EXCEDE el precio referencial"
        avisos.append("La propuesta sobrepasa el precio referencial: revisa en el DBC qué consecuencia tiene.")
    elif tp < minimo:
        estado = f"Por debajo del {pct_minimo} % del precio referencial: garantía adicional"
    else:
        estado = f"OK: entre {pct_minimo} % y 100 % del precio referencial"
    return ControlPropuesta(
        precio_referencial=_q(pr), total_propuesta=_q(tp), porcentaje_del_referencial=(tp / pr * 100).quantize(Decimal("0.0001")),
        diferencia=_q(tp - pr), excede_referencial=excede, umbral_85=_q(minimo), garantia_adicional=_q(adicional),
        garantia_cumplimiento=_q(tp * pc / 100), garantia_seriedad=_q(pr * Decimal(str(pct_seriedad)) / 100),
        estado=estado, avisos=avisos)
