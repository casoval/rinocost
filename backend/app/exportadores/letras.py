"""Importe en letras en el formato del B-1: 'Doce 50/100 Bolivianos'."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Union

_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
             "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
             "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
             "veintinueve"]
_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
_CENTENAS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos", 6: "seiscientos",
             7: "setecientos", 8: "ochocientos", 9: "novecientos"}


def _apocopar(texto: str) -> str:
    """'uno' -> 'un' y 'veintiuno' -> 'veintiún' (delante de 'mil', 'millones' y 'Bolivianos')."""
    if texto.endswith("veintiuno"):
        return texto[: -len("veintiuno")] + "veintiún"
    if texto.endswith("uno"):
        return texto[:-3] + "un"
    return texto


def _menor_mil(n: int) -> str:
    if n == 100:
        return "cien"
    partes = []
    c, r = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if r:
        if r < 30:
            partes.append(_UNIDADES[r])
        else:
            d, u = divmod(r, 10)
            partes.append(_DECENAS[d] + (f" y {_UNIDADES[u]}" if u else ""))
    return " ".join(partes)


def _entero(n: int) -> str:
    if n == 0:
        return "cero"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    if millones:
        partes.append("un millón" if millones == 1 else f"{_apocopar(_entero(millones))} millones")
    if miles:
        partes.append("mil" if miles == 1 else f"{_apocopar(_menor_mil(miles))} mil")
    if unidades:
        partes.append(_menor_mil(unidades))
    return " ".join(partes)


def numero_a_letras(valor: Union[Decimal, float, int, str]) -> str:
    v = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if v < 0:
        raise ValueError("El importe no puede ser negativo.")
    entero = int(v)
    centavos = int((v - entero) * 100)
    texto = _apocopar(_entero(entero))
    return f"{texto[0].upper()}{texto[1:]} {centavos:02d}/100 Bolivianos"
