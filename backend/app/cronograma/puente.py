"""Convierte un proyecto (ítems con APU) en actividades del cronograma. Sin dependencias de base de datos:
usa solo atributos (item.cantidad, item.apu.lineas, item.datos_tecnicos...), así se puede probar aparte."""
from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any, Optional

from ..importers.b1_parser import normalizar_unidad
from .motor import Actividad

_ESPERA_RE = re.compile(r"(\d+)(?:\s*a\s*(\d+))?\s*(dias|horas)", re.IGNORECASE)


def _esperas(item: Any) -> tuple[int, int, str]:
    """(días corridos de espera tras terminar, días mínimos de duración, nota) según los datos técnicos del pliego."""
    corridos, minimo, notas = 0, 1, []
    for d in getattr(item, "datos_tecnicos", []) or []:
        if d.tipo != "espera":
            continue
        m = _ESPERA_RE.search(str(d.valor))
        if not m:
            continue
        n = int(m.group(2) or m.group(1))
        if m.group(3).lower() == "dias":
            corridos = max(corridos, n)
            notas.append(f"espera de {n} días (pliego)")
        elif n >= 24:  # 24 horas o más obligan a que el trabajo dure al menos ese tiempo
            minimo = max(minimo, math.ceil(n / 24))
            notas.append(f"{n} horas de espera/secado (pliego)")
    return corridos, minimo, "; ".join(notas)


def actividades_del_proyecto(
    proyecto: Any, personas_defecto: int, personas_por_item: dict[int, int], horas_jornada: Decimal,
) -> tuple[list[Actividad], list[tuple[Any, str]]]:
    """Devuelve (actividades, sin_programar). Un ítem solo se programa si su APU tiene mano de obra COMPLETA:
    nunca se inventa una duración."""
    actividades: list[Actividad] = []
    sin: list[tuple[Any, str]] = []
    for modulo in proyecto.modulos:
        for item in modulo.items:
            apu = getattr(item, "apu", None)
            if apu is None:
                sin.append((item, "No tiene APU."))
                continue
            mano = [l for l in apu.lineas if l.tipo == "mano_obra"]
            if not mano:
                sin.append((item, "Su APU no tiene mano de obra."))
                continue
            if any(l.cantidad is None for l in mano):
                sin.append((item, "Faltan cantidades de mano de obra en su APU."))
                continue
            if item.cantidad is None or Decimal(item.cantidad) <= 0:
                sin.append((item, "La cantidad del ítem es cero o no es válida."))
                continue
            notas: list[str] = []
            horas_por_unidad = Decimal(0)
            for l in mano:
                unidad = normalizar_unidad(l.unidad or "")
                factor = horas_jornada if unidad == "dia" else Decimal(1)
                if unidad not in ("h", "dia", ""):
                    notas.append(f"unidad de mano de obra «{l.unidad}» tomada como horas-hombre")
                horas_por_unidad += Decimal(l.cantidad) * factor
            horas = horas_por_unidad * Decimal(item.cantidad)
            if horas <= 0:
                sin.append((item, "La mano de obra del APU suma cero horas."))
                continue
            corridos, minimo, nota_espera = _esperas(item)
            if nota_espera:
                notas.append(nota_espera)
            actividades.append(Actividad(
                id=item.id, modulo=modulo.id, numero=item.numero, nombre=item.descripcion, horas_hombre=horas,
                personas=max(1, int(personas_por_item.get(item.id, personas_defecto))),
                espera_calendario=corridos, duracion_minima=minimo, nota="; ".join(notas),
            ))
    return actividades, sin
