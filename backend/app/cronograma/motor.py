"""Cronograma de ejecución: duraciones desde la mano de obra, secuencia por módulos, ruta crítica y hitos.

Duración (días hábiles) = ceil( horas-hombre ÷ (personas × horas de jornada) ), con mínimo de 1 día.
Las esperas obligatorias en días CORRIDOS (p. ej. 21 días de fraguado) se convierten a días hábiles
según la semana de trabajo (aprox. = ceil(días × días_hábiles_por_semana ÷ 7)) y retrasan a los sucesores.
Todo el cálculo se hace con índices de días hábiles; las fechas salen del calendario (sábados y feriados).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Optional, Sequence

SECUENCIAS = ("modulos_en_serie", "todo_en_serie", "todo_en_paralelo", "frentes_de_trabajo")


@dataclass(frozen=True)
class Parametros:
    fecha_inicio: date
    horas_jornada: Decimal = Decimal("8")
    trabaja_sabados: bool = False
    feriados: frozenset = frozenset()
    secuencia: str = "modulos_en_serie"
    frentes: int = 1  # solo con secuencia «frentes_de_trabajo»: cuántos frentes trabajan en paralelo


@dataclass
class Actividad:
    id: int  # id del ítem
    modulo: int  # id del módulo
    numero: int
    nombre: str
    horas_hombre: Decimal
    personas: int
    espera_calendario: int = 0  # días corridos de espera obligatoria al terminar
    duracion_minima: int = 1  # días hábiles (p. ej. una espera de 48 horas obliga a 2)
    nota: str = ""


@dataclass
class ActividadCalculada:
    actividad: Actividad
    duracion: int
    inicio: date
    fin: date
    holgura: int
    critica: bool
    espera_laborables: int
    predecesoras: list[int] = field(default_factory=list)  # ids de los ítems que fijan su inicio (los que «empujan»)
    frente: int = 0  # N° de frente (1, 2, …) con «todo_en_serie» (un solo frente) y «frentes_de_trabajo»; 0 en las demás


@dataclass
class ModuloCalculado:
    id: int
    inicio: Optional[date]
    fin: Optional[date]
    hito: Optional[date]
    atraso_dias: int  # días hábiles de atraso respecto del hito
    dias_habiles: int = 0  # días hábiles entre su primera y su última actividad


@dataclass
class ResultadoCronograma:
    actividades: list[ActividadCalculada] = field(default_factory=list)
    modulos: list[ModuloCalculado] = field(default_factory=list)
    fecha_fin: Optional[date] = None
    dias_habiles: int = 0


class Calendario:
    """Días hábiles consecutivos desde la fecha de inicio (lunes a viernes, o a sábado; sin feriados)."""

    LIMITE_DIAS = 20000

    def __init__(self, p: Parametros) -> None:
        self.p = p
        self.dias_semana = 6 if p.trabaja_sabados else 5
        self._dias: list[date] = []
        self._cursor = p.fecha_inicio - timedelta(days=1)

    def es_habil(self, d: date) -> bool:
        return d.weekday() < self.dias_semana and d not in self.p.feriados

    def fecha(self, indice: int) -> date:
        if indice < 0:
            raise ValueError("Índice de día negativo.")
        while len(self._dias) <= indice:
            self._cursor += timedelta(days=1)
            if (self._cursor - self.p.fecha_inicio).days > self.LIMITE_DIAS:
                raise ValueError("El cronograma supera el límite de días; revisa el calendario y las duraciones.")
            if self.es_habil(self._cursor):
                self._dias.append(self._cursor)
        return self._dias[indice]

    def laborables(self, corridos: int) -> int:
        return math.ceil(corridos * self.dias_semana / 7) if corridos > 0 else 0

    def habiles_entre(self, desde: date, hasta: date) -> int:
        """Días hábiles en (desde, hasta]."""
        n, d = 0, desde
        while d < hasta:
            d += timedelta(days=1)
            if self.es_habil(d):
                n += 1
        return n


@dataclass
class _Nodo:
    dur: int
    preds: list[tuple[str, int]]  # (clave del predecesor, espera en días hábiles tras terminar)
    actividad: Optional[Actividad] = None


def duracion_dias(a: Actividad, horas_jornada: Decimal) -> int:
    personas = Decimal(max(1, a.personas))
    por_trabajo = int((a.horas_hombre / (personas * horas_jornada)).to_integral_value(rounding=ROUND_CEILING))
    return max(1, a.duracion_minima, por_trabajo)


def personas_necesarias(horas_hombre: Decimal, dias: int, horas_jornada: Decimal) -> int:
    """Cuántas personas hacen falta para terminar un trabajo en `dias` días hábiles."""
    if dias <= 0:
        raise ValueError("Los días disponibles deben ser positivos.")
    return max(1, int((horas_hombre / (Decimal(dias) * horas_jornada)).to_integral_value(rounding=ROUND_CEILING)))


def repartir_en_frentes(actividades: Sequence[Actividad], k: int, horas_jornada: Decimal = Decimal("8")) -> dict[int, int]:
    """Reparte las actividades (ya en orden de ejecución) en `k` frentes: {id de actividad: N° de frente, desde 1}.

    Heurística de equilibrio: cada actividad pesa por sus horas-hombre y por su tiempo FIJO (al menos 1 día, más la espera
    obligatoria y la duración mínima), porque el tiempo fijo no se acorta poniendo más gente. Se reparte de la más pesada a la
    más liviana, siempre al frente con menos carga. Dentro de cada frente se mantiene el orden original.
    No depende de las personas asignadas: el reparto es estable mientras el optimizador cambia las cuadrillas."""
    acts = list(actividades)
    k = max(1, min(int(k), len(acts) or 1))
    if k == 1:
        return {a.id: 1 for a in acts}
    fijo = {a.id: max(1, a.duracion_minima) + a.espera_calendario for a in acts}
    tot_hh = sum((a.horas_hombre for a in acts), Decimal(0)) or Decimal(1)
    tot_fijo = sum(fijo.values()) or 1
    peso = {a.id: float(a.horas_hombre / tot_hh) + fijo[a.id] / tot_fijo for a in acts}
    carga = [0.0] * k
    out: dict[int, int] = {}
    for a in sorted(acts, key=lambda a: -peso[a.id]):  # estable: en empate se respeta el orden original
        f = min(range(k), key=lambda i: (carga[i], i))
        carga[f] += peso[a.id]
        out[a.id] = f + 1
    return out


def calcular(
    actividades: Sequence[Actividad], modulos_orden: Sequence[int], p: Parametros,
    hitos: Optional[dict[int, date]] = None,
) -> ResultadoCronograma:
    if p.secuencia not in SECUENCIAS:
        raise ValueError(f"Secuencia no válida: {p.secuencia!r}. Usa una de {SECUENCIAS}.")
    if p.horas_jornada <= 0:
        raise ValueError("Las horas de jornada deben ser positivas.")
    cal = Calendario(p)
    por_modulo: dict[int, list[Actividad]] = {}
    for a in actividades:
        por_modulo.setdefault(a.modulo, []).append(a)
    orden = list(modulos_orden) + [m for m in por_modulo if m not in modulos_orden]

    def espera(a: Actividad) -> int:
        return cal.laborables(a.espera_calendario)

    nodos: dict[str, _Nodo] = {}
    frente_de: dict[int, int] = {}
    if p.secuencia == "modulos_en_serie":
        previo: Optional[str] = None  # un módulo sin actividades no corta la cadena
        for mid in orden:
            acts = sorted(por_modulo.get(mid, []), key=lambda a: a.numero)
            for a in acts:
                nodos[f"a{a.id}"] = _Nodo(duracion_dias(a, p.horas_jornada), [(previo, 0)] if previo else [], a)
            if acts:
                nodos[f"m{mid}"] = _Nodo(0, [(f"a{a.id}", espera(a)) for a in acts])
                previo = f"m{mid}"
    elif p.secuencia == "frentes_de_trabajo":
        en_orden = [a for mid in orden for a in sorted(por_modulo.get(mid, []), key=lambda a: a.numero)]
        frente_de = repartir_en_frentes(en_orden, p.frentes, p.horas_jornada)
        ultima_del_frente: dict[int, Actividad] = {}  # cada frente hace sus actividades una tras otra
        for a in en_orden:
            f = frente_de[a.id]
            prev = ultima_del_frente.get(f)
            nodos[f"a{a.id}"] = _Nodo(duracion_dias(a, p.horas_jornada), [(f"a{prev.id}", espera(prev))] if prev else [], a)
            ultima_del_frente[f] = a
    else:
        previa: Optional[Actividad] = None
        for mid in orden:
            for a in sorted(por_modulo.get(mid, []), key=lambda a: a.numero):
                preds = [(f"a{previa.id}", espera(previa))] if (p.secuencia == "todo_en_serie" and previa) else []
                nodos[f"a{a.id}"] = _Nodo(duracion_dias(a, p.horas_jornada), preds, a)
                previa = a

    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    for k, n in nodos.items():  # el orden de inserción ya es topológico
        es[k] = max((ef[pk] + lag for pk, lag in n.preds), default=0)
        ef[k] = es[k] + n.dur
    fin_proyecto = max(ef.values(), default=0)

    sucesores: dict[str, list[tuple[str, int]]] = {k: [] for k in nodos}
    for k, n in nodos.items():
        for pk, lag in n.preds:
            sucesores[pk].append((k, lag))
    ls: dict[str, int] = {}
    for k in reversed(list(nodos)):
        lf = min((ls[sk] - lag for sk, lag in sucesores[k]), default=fin_proyecto)
        ls[k] = lf - nodos[k].dur

    def impulsores(k: str) -> list[int]:
        """Ítems predecesores que determinan el inicio de `k` (los módulos intermedios se atraviesan)."""
        out: list[int] = []
        for pk, lag in nodos[k].preds:
            if ef[pk] + lag != es[k]:
                continue
            if nodos[pk].actividad is not None:
                out.append(nodos[pk].actividad.id)
            else:
                out.extend(impulsores(pk))
        return sorted(set(out))

    res = ResultadoCronograma(dias_habiles=fin_proyecto)
    calculadas: dict[int, ActividadCalculada] = {}
    for k, n in nodos.items():
        if n.actividad is None:
            continue
        holgura = ls[k] - es[k]
        c = ActividadCalculada(n.actividad, n.dur, cal.fecha(es[k]), cal.fecha(ef[k] - 1), holgura, holgura == 0,
                               espera(n.actividad), impulsores(k),
                               frente_de.get(n.actividad.id, 0) if p.secuencia == "frentes_de_trabajo"
                               else (1 if p.secuencia == "todo_en_serie" else 0))
        res.actividades.append(c)
        calculadas[n.actividad.id] = c
    res.fecha_fin = max((c.fin for c in res.actividades), default=None)

    for mid in orden:
        cs = [calculadas[a.id] for a in por_modulo.get(mid, [])]
        inicio = min((c.inicio for c in cs), default=None)
        fin = max((c.fin for c in cs), default=None)
        hito = (hitos or {}).get(mid)
        atraso = cal.habiles_entre(hito, fin) if hito and fin and fin > hito else 0
        claves = [f"a{a.id}" for a in por_modulo.get(mid, [])]
        dias_mod = (max(ef[k] for k in claves) - min(es[k] for k in claves)) if claves else 0
        res.modulos.append(ModuloCalculado(mid, inicio, fin, hito, atraso, dias_mod))
    return res
