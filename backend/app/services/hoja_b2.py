"""Hoja B-2 de un ítem (análisis de precio unitario), calculada en el servidor.

El navegador solo la muestra: usa el mismo motor (`costos.calcular`) que el PDF y el Excel,
con Decimal y sin redondeos intermedios, así que las tres salidas coinciden.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from ..costos import ModeloCostos, calcular, obtener_predefinido

_CENT = Decimal("0.01")


def _costo(l: dict) -> Optional[str]:
    if l.get("cantidad") is None or l.get("precio_unitario") is None:
        return None
    return str((Decimal(l["cantidad"]) * Decimal(l["precio_unitario"])).quantize(_CENT, rounding=ROUND_HALF_UP))


def construir_hoja_b2(proyecto: dict, item: dict) -> dict:
    """`proyecto` e `item` son los diccionarios de ProyectoOut / ItemOut (model_dump)."""
    apu = item.get("apu")
    modelo = proyecto.get("modelo_costos") or obtener_predefinido("costo_directo").a_dict()
    lineas = (apu or {}).get("lineas") or []
    pendientes = sum(1 for l in lineas if l.get("cantidad") is None or l.get("precio_unitario") is None)
    completo = bool(lineas) and pendientes == 0

    resultado = None
    if completo:
        directos = {"material": Decimal(0), "mano_obra": Decimal(0), "equipo": Decimal(0)}
        for l in lineas:
            directos[l["tipo"]] += Decimal(l["cantidad"]) * Decimal(l["precio_unitario"])
        resultado = calcular(ModeloCostos.desde_dict(modelo), directos["material"], directos["mano_obra"], directos["equipo"])
    valor = {l.codigo: l.valor for l in resultado.lineas} if resultado else {}
    base_de = {l.codigo: l.base for l in resultado.lineas} if resultado else {}

    secciones = []
    n = 0
    for s in modelo["secciones"]:
        if not s.get("activo", True):
            continue
        n += 1
        tipo = s.get("tipo_recurso")
        del_tipo = [l for l in lineas if tipo and l["tipo"] == tipo]
        secciones.append({
            "numero": n, "codigo": s["codigo"], "titulo": s["titulo"], "tipo_recurso": tipo,
            "etiqueta_total": s.get("etiqueta_total") or f"TOTAL {s['titulo']}",
            "lineas": [{
                "n": k, "id": l.get("id"), "descripcion": l["descripcion"], "unidad": l["unidad"], "cantidad": l.get("cantidad"),
                "precio_unitario": l.get("precio_unitario"), "costo": _costo(l),
            } for k, l in enumerate(del_tipo, start=1)],
            "subtotal_directo": None if resultado is None else str(valor.get(f"{s['codigo']}.directo", 0)),
            "pasos": [{
                "codigo": q["codigo"], "etiqueta": q["etiqueta"].replace("{pct}", str(q["porcentaje"]).replace(".", ",")),
                "porcentaje": q["porcentaje"], "bases": q.get("base", []),
                "base_valor": None if resultado is None or base_de.get(q["codigo"]) is None else str(base_de[q["codigo"]]),
                "importe": None if resultado is None else str(valor.get(q["codigo"], 0)),
            } for q in s.get("pasos", []) if q.get("activo", True)],
            "total": None if resultado is None else str(resultado.secciones.get(s["codigo"], 0)),
        })

    parcial = {"material": Decimal(0), "mano_obra": Decimal(0), "equipo": Decimal(0)}
    for l in lineas:  # subtotal por tipo con las líneas que ya tienen cantidad y precio (para mostrar avance)
        c = _costo(l)
        if c is not None:
            parcial[l["tipo"]] += Decimal(c)

    return {
        "subtotal_por_tipo": {k: str(v) for k, v in parcial.items()},
        "proyecto": proyecto["nombre"],
        "item": {"id": item["id"], "numero": item["numero"], "descripcion": item["descripcion"], "unidad": item["unidad"],
                 "cantidad": item.get("cantidad"), "cantidad_texto": item.get("cantidad_texto", "")},
        "modelo": {"codigo": modelo.get("codigo", ""), "nombre": modelo.get("nombre", ""), "decimales": int(modelo.get("decimales", 2))},
        "tiene_apu": bool(lineas), "completo": completo, "pendientes": pendientes,
        "secciones": secciones,
        "total_sin_redondeo": None if resultado is None else str(resultado.total),
        "precio_adoptado": None if resultado is None else str(resultado.precio),
        "directos": None if resultado is None else {k: str(v) for k, v in resultado.directos.items()},
    }
