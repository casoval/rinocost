"""Modelos de costos listos para usar. Son PUNTOS DE PARTIDA: al crear un proyecto se copian y se pueden editar.

Importante: el D.S. 0181 (NB-SABS) fija garantías, anticipo y reglas de contratación, pero NO fija la estructura del
Formulario B-2 ni los porcentajes de cargas sociales, IVA de mano de obra, herramientas, gastos generales, utilidad
e IT. Esos vienen del Documento Base de Contratación (modelo del Órgano Rector) y de cada convocatoria, y varían.
Por eso los porcentajes de abajo son valores iniciales (los usados en la planilla de referencia del proyecto
Alonso de Ibáñez D-11) y cada proyecto los puede cambiar.
"""
from __future__ import annotations

from decimal import Decimal

from .modelo import ModeloCostos, Paso, Seccion

NOTA_B2 = ("Estructura del Formulario B-2 (análisis de precios unitarios) del DBC. Los porcentajes son valores "
           "iniciales editables: cada convocatoria define los suyos y el proponente debe señalarlos. Los precios de materiales y "
           "equipo se ingresan sin IVA (87 % del precio de factura, porque la compra con factura da crédito fiscal).")


def _b2(pct_cargas="55", pct_iva_mo="14.94", pct_herr="5", pct_gg="10", pct_util="10", pct_it="3.09") -> ModeloCostos:
    return ModeloCostos(
        codigo="bolivia_b2", nombre="Bolivia – Formulario B-2 (obra pública)",
        descripcion="Materiales, mano de obra con cargas sociales e IVA, herramientas, gastos generales, utilidad e IT.",
        nota=NOTA_B2, decimales=2,
        secciones=[
            Seccion("materiales", "MATERIALES", "material", etiqueta_total="TOTAL MATERIALES"),
            Seccion("mano_obra", "MANO DE OBRA", "mano_obra", etiqueta_total="TOTAL MANO DE OBRA", pasos=[
                Paso("cargas_sociales", "CARGAS SOCIALES = {pct}% DEL SUBTOTAL DE MANO DE OBRA", Decimal(pct_cargas),
                     ["mano_obra.directo"], minimo=Decimal("55"), maximo=Decimal("71.18"),
                     ayuda="Beneficios sociales sobre el subtotal de mano de obra. Rango de referencia 55 %–71,18 %; el más habitual es 55 %."),
                Paso("iva_mo", "IMPUESTOS IVA MANO DE OBRA = {pct}% DE SUMA DE SUBTOTAL DE MANO DE OBRA + CARGAS SOCIALES",
                     Decimal(pct_iva_mo), ["mano_obra.directo", "cargas_sociales"],
                     ayuda="Tasa efectiva 13/87 = 14,94 %, sobre mano de obra + cargas sociales (no genera crédito fiscal)."),
            ]),
            Seccion("equipo", "EQUIPO, MAQUINARIA Y HERRAMIENTAS", "equipo",
                    etiqueta_total="TOTAL EQUIPO, MAQUINARIA Y HERRAMIENTAS", pasos=[
                Paso("herramientas", "HERRAMIENTAS = {pct}% DEL TOTAL DE MANO DE OBRA", Decimal(pct_herr), ["mano_obra"],
                     minimo=Decimal("5"), maximo=Decimal("6"), ayuda="Sobre el TOTAL de mano de obra (subtotal + cargas + IVA). Habitual 5 %–6 %."),
            ]),
            Seccion("gastos_generales", "GASTOS GENERALES Y ADMINISTRATIVOS", None,
                    etiqueta_total="TOTAL GASTOS GENERALES Y ADMINISTRATIVOS", pasos=[
                Paso("gg", "GASTOS GENERALES = {pct}% DE 1 + 2 + 3", Decimal(pct_gg), ["materiales", "mano_obra", "equipo"],
                     minimo=Decimal("8"), maximo=Decimal("15"), ayuda="Sobre 1 + 2 + 3. Suele oscilar entre 8 % y 15 %; 10 % es el valor más común."),
            ]),
            Seccion("utilidad", "UTILIDAD", None, etiqueta_total="TOTAL UTILIDAD", pasos=[
                Paso("util", "UTILIDAD = {pct}% DE 1 + 2 + 3 + 4", Decimal(pct_util),
                     ["materiales", "mano_obra", "equipo", "gastos_generales"],
                     minimo=Decimal("5"), maximo=Decimal("10"), ayuda="Sobre 1 + 2 + 3 + 4. Habitual 5 %–10 %."),
            ]),
            Seccion("impuestos", "IMPUESTOS", None, etiqueta_total="TOTAL IMPUESTOS", pasos=[
                Paso("it", "IMPUESTOS IT = {pct}% DE 1 + 2 + 3 + 4 + 5", Decimal(pct_it),
                     ["materiales", "mano_obra", "equipo", "gastos_generales", "utilidad"],
                     ayuda="Tasa efectiva 3/97 = 3,09 %, sobre 1 + 2 + 3 + 4 + 5, para recuperar el 3 % nominal del IT."),
            ]),
        ])


b2_con_porcentajes = _b2  # constructor público: b2_con_porcentajes(pct_cargas="55", pct_gg="10", ...)


def _privado_simple() -> ModeloCostos:
    return ModeloCostos(
        codigo="privado_simple", nombre="Obra privada – simple",
        descripcion="Costo directo + gastos generales + utilidad. Sin desglose de cargas ni impuestos (ajústalo a tu criterio).",
        nota="Valores iniciales de ejemplo: el presupuestista decide cada porcentaje.", decimales=2,
        secciones=[
            Seccion("materiales", "MATERIALES", "material", etiqueta_total="TOTAL MATERIALES"),
            Seccion("mano_obra", "MANO DE OBRA", "mano_obra", etiqueta_total="TOTAL MANO DE OBRA"),
            Seccion("equipo", "EQUIPO Y HERRAMIENTAS", "equipo", etiqueta_total="TOTAL EQUIPO Y HERRAMIENTAS"),
            Seccion("gastos_generales", "GASTOS GENERALES", None, etiqueta_total="TOTAL GASTOS GENERALES", pasos=[
                Paso("gg", "GASTOS GENERALES = {pct}% DEL COSTO DIRECTO", Decimal("10"), ["materiales", "mano_obra", "equipo"]),
            ]),
            Seccion("utilidad", "UTILIDAD", None, etiqueta_total="TOTAL UTILIDAD", pasos=[
                Paso("util", "UTILIDAD = {pct}% DE COSTO DIRECTO + GASTOS GENERALES", Decimal("10"),
                     ["materiales", "mano_obra", "equipo", "gastos_generales"]),
            ]),
        ])


def _solo_directo() -> ModeloCostos:
    return ModeloCostos(
        codigo="costo_directo", nombre="Solo costo directo",
        descripcion="Sin indirectos: el precio unitario es la suma de materiales, mano de obra y equipo.", decimales=2,
        secciones=[
            Seccion("materiales", "MATERIALES", "material", etiqueta_total="TOTAL MATERIALES"),
            Seccion("mano_obra", "MANO DE OBRA", "mano_obra", etiqueta_total="TOTAL MANO DE OBRA"),
            Seccion("equipo", "EQUIPO Y HERRAMIENTAS", "equipo", etiqueta_total="TOTAL EQUIPO Y HERRAMIENTAS"),
        ])


MODELOS_PREDEFINIDOS = {"bolivia_b2": _b2, "privado_simple": _privado_simple, "costo_directo": _solo_directo}


def obtener_predefinido(codigo: str) -> ModeloCostos:
    """Devuelve una COPIA nueva (editarla no cambia el predefinido)."""
    try:
        return MODELOS_PREDEFINIDOS[codigo]()
    except KeyError:
        raise KeyError(f"No hay un modelo predefinido '{codigo}'. Disponibles: {', '.join(MODELOS_PREDEFINIDOS)}") from None
