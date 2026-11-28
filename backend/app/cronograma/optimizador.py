"""Ajuste del cronograma a un plazo máximo y búsqueda del tiempo óptimo.

La mano de obra total (horas-hombre) de cada ítem NO cambia al poner más gente: lo que cambia es la duración.
Por eso «acelerar» solo tiene sentido sobre las actividades de la RUTA CRÍTICA (las que no tienen holgura):
acortar una actividad con holgura no acorta la obra.

Objetivos:
- manual:        se respetan las personas que puso el usuario.
- cumplir_plazo: se suman personas, de una en una, a la actividad crítica que más días ahorra por persona agregada,
                 hasta entrar en el plazo máximo (la forma que menos gente suma para cumplirlo).
- mas_rapido:    se acelera la ruta crítica hasta donde permita el tope de personas por actividad.
- Si con la secuencia elegida el plazo es imposible (p. ej. 24 ítems «uno tras otro» ya suman más días que el plazo), se
  ABREN FRENTES: las actividades se reparten en k frentes en paralelo, cada uno hace las suyas una tras otra, y se busca el
  MENOR k que alcance. Luego se calcula la cuadrilla de cada frente y el personal total (ver `abrir_frentes`).
- menor_costo:   suma personas mientras el ahorro por terminar antes (gastos indirectos diarios) supere el costo de
                 incorporarlas. Necesita esos dos datos: sin ellos no se inventa un óptimo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from .motor import (
    Actividad, ActividadCalculada, Parametros, ResultadoCronograma, calcular, duracion_dias, repartir_en_frentes,
)

OBJETIVOS = ("manual", "cumplir_plazo", "mas_rapido", "menor_costo")
TIPOS_PLAZO = ("calendario", "habiles")
_MAX_PASOS = 3000


@dataclass(frozen=True)
class Plazo:
    maximo: Optional[int] = None  # días; None = sin plazo
    tipo: str = "calendario"  # 'calendario' o 'habiles'


@dataclass(frozen=True)
class Costos:
    indirecto_dia: Decimal = Decimal(0)  # Bs por día CALENDARIO de obra (gastos generales, supervisión, alquileres)
    por_persona: Decimal = Decimal(0)  # Bs por cada persona adicional que se incorpora (movilización, equipo, etc.)


@dataclass
class Escenario:
    clave: str
    personas: dict[int, int]
    resultado: ResultadoCronograma
    dias_calendario: int
    dias_habiles: int
    pico_personas: int
    personas_agregadas: int
    costo_plazo: Decimal  # indirecto_dia × días calendario
    costo_movilizacion: Decimal
    avisos: list[str] = field(default_factory=list)
    secuencia: str = ""
    frentes: int = 0  # frentes de trabajo (0 si la secuencia no los define)
    personal_total: int = 0  # personal a contratar: suma de la cuadrilla (máxima) de cada frente; sin frentes = pico

    @property
    def costo_total(self) -> Decimal:
        return self.costo_plazo + self.costo_movilizacion


def dias_calendario(res: ResultadoCronograma, inicio: date) -> int:
    """Días corridos desde la fecha de inicio (día 1) hasta el último día de obra, ambos incluidos."""
    return (res.fecha_fin - inicio).days + 1 if res.fecha_fin else 0


def dias_del_plazo(res: ResultadoCronograma, inicio: date, tipo: str) -> int:
    return res.dias_habiles if tipo == "habiles" else dias_calendario(res, inicio)


def pico_de_personas(res: ResultadoCronograma) -> int:
    """Máximo de personas trabajando el mismo día (suma de las actividades que se solapan)."""
    cambios: dict[int, int] = {}
    for c in res.actividades:
        cambios[c.inicio.toordinal()] = cambios.get(c.inicio.toordinal(), 0) + c.actividad.personas
        cambios[c.fin.toordinal() + 1] = cambios.get(c.fin.toordinal() + 1, 0) - c.actividad.personas
    actual = pico = 0
    for d in sorted(cambios):
        actual += cambios[d]
        pico = max(pico, actual)
    return pico


class Optimizador:
    def __init__(
        self, actividades: Sequence[Actividad], modulos_orden: Sequence[int], p: Parametros,
        hitos: Optional[dict[int, date]], base: dict[int, int], tope: int, plazo: Plazo, costos: Costos,
    ) -> None:
        if plazo.tipo not in TIPOS_PLAZO:
            raise ValueError(f"Tipo de plazo no válido: {plazo.tipo!r}. Usa uno de {TIPOS_PLAZO}.")
        self.acts = list(actividades)
        self.por_id = {a.id: a for a in self.acts}
        self.orden, self.p, self.hitos = list(modulos_orden), p, hitos
        self.base = {a.id: max(1, base.get(a.id, a.personas)) for a in self.acts}
        self.tope, self.plazo, self.costos = max(1, tope), plazo, costos

    # ---- cálculo ----------------------------------------------------------------------------------------
    def _calcular(self, personas: dict[int, int]) -> ResultadoCronograma:
        return calcular([replace(a, personas=personas[a.id]) for a in self.acts], self.orden, self.p, self.hitos)

    def _dur(self, a: Actividad, n: int) -> int:
        return duracion_dias(replace(a, personas=n), self.p.horas_jornada)

    def _siguiente(self, c: ActividadCalculada, personas: dict[int, int]) -> Optional[tuple[int, int]]:
        """(personas nuevas, días ahorrados) con el menor aumento de gente que de verdad acorta la actividad."""
        a, n0 = self.por_id[c.actividad.id], personas[c.actividad.id]
        d0 = self._dur(a, n0)
        for n in range(n0 + 1, self.tope + 1):
            d = self._dur(a, n)
            if d < d0:
                return n, d0 - d
        return None

    def _escenario(self, clave: str, personas: dict[int, int], res: Optional[ResultadoCronograma] = None) -> Escenario:
        res = res or self._calcular(personas)
        cal = dias_calendario(res, self.p.fecha_inicio)
        extra = sum(max(0, personas[i] - self.base[i]) for i in personas)
        pico = pico_de_personas(res)
        por_frente: dict[int, int] = {}
        for c in res.actividades:
            if c.frente:
                por_frente[c.frente] = max(por_frente.get(c.frente, 0), c.actividad.personas)
        return Escenario(
            clave, dict(personas), res, cal, res.dias_habiles, pico, extra,
            self.costos.indirecto_dia * cal, self.costos.por_persona * extra,
            secuencia=self.p.secuencia, frentes=len(por_frente), personal_total=sum(por_frente.values()) or pico,
        )

    def _candidatos(self, res: ResultadoCronograma, personas: dict[int, int]):
        out = []
        for c in res.actividades:
            if not c.critica:
                continue
            sig = self._siguiente(c, personas)
            if sig:
                out.append((c, sig[0], sig[1]))
        return out

    # ---- estrategias ------------------------------------------------------------------------------------
    def manual(self) -> Escenario:
        return self._escenario("manual", dict(self.base))

    def cumplir_plazo(self) -> Escenario:
        if self.plazo.maximo is None:
            raise ValueError("Indica el plazo máximo para usar «Cumplir el plazo».")
        personas = self._sembrar() if self.p.secuencia == "frentes_de_trabajo" else dict(self.base)
        res = self._calcular(personas)
        for _ in range(_MAX_PASOS):
            if dias_del_plazo(res, self.p.fecha_inicio, self.plazo.tipo) <= self.plazo.maximo:
                break
            cands = self._candidatos(res, personas)
            if not cands:
                break
            # la que más días ahorra por cada persona que se agrega (en empate, la que más ahorra)
            c, n, ahorro = max(cands, key=lambda t: (t[2] / (t[1] - personas[t[0].actividad.id]), t[2]))
            personas[c.actividad.id] = n
            res = self._calcular(personas)
        if self.p.secuencia == "frentes_de_trabajo" and self._cumple(res):
            personas = self._recortar(personas)  # quita el exceso que dejó el redondeo de la siembra
            res = self._calcular(personas)
        return self._escenario("cumplir_plazo", personas, res)

    # ---- frentes de trabajo -----------------------------------------------------------------------------
    def _cumple(self, res: ResultadoCronograma) -> bool:
        return self.plazo.maximo is not None and dias_del_plazo(res, self.p.fecha_inicio, self.plazo.tipo) <= self.plazo.maximo

    def con_frentes(self, k: int) -> "Optimizador":
        p2 = replace(self.p, secuencia="frentes_de_trabajo", frentes=k)
        return Optimizador(self.acts, self.orden, p2, self.hitos, self.base, self.tope, self.plazo, self.costos)

    def _sembrar(self) -> dict[int, int]:
        """Cuadrilla inicial de cada frente: todas sus actividades con la misma gente, la justa para entrar en el plazo
        (horas-hombre del frente ÷ (días disponibles × jornada)). Después se repara y se recorta con el cálculo real."""
        personas = dict(self.base)
        sem = 6 if self.p.trabaja_sabados else 5
        total = self.plazo.maximo or 1
        habiles = total if self.plazo.tipo == "habiles" else max(1, (total * sem) // 7)
        orden = [a for m in self.orden for a in sorted((x for x in self.acts if x.modulo == m), key=lambda x: x.numero)]
        orden += [a for a in self.acts if a not in orden]
        frente_de = repartir_en_frentes(orden, self.p.frentes, self.p.horas_jornada)
        grupos: dict[int, list[Actividad]] = {}
        for a in orden:
            grupos.setdefault(frente_de[a.id], []).append(a)
        for acts in grupos.values():
            esperas = sum(math.ceil(a.espera_calendario * sem / 7) for a in acts)
            libres = max(len(acts), habiles - esperas)
            hh = sum((a.horas_hombre for a in acts), Decimal(0))
            cuadrilla = max(1, math.ceil(hh / (Decimal(libres) * self.p.horas_jornada)))
            for a in acts:
                personas[a.id] = max(personas[a.id], min(self.tope, cuadrilla))
        return personas

    def _recortar(self, personas: dict[int, int]) -> dict[int, int]:
        """Baja gente mientras el plazo se siga cumpliendo (empezando por las cuadrillas más grandes)."""
        personas = dict(personas)
        intentos = 0
        for _ in range(3):
            cambio = False
            for i in sorted(personas, key=lambda x: -personas[x]):
                while personas[i] > self.base[i] and intentos < 1500:
                    personas[i] -= 1
                    intentos += 1
                    if self._cumple(self._calcular(personas)):
                        cambio = True
                    else:
                        personas[i] += 1
                        break
            if not cambio:
                break
        return personas

    def _minimo_con_tope(self) -> ResultadoCronograma:
        """Duración más corta posible con la secuencia actual: todas las actividades con el tope de personas."""
        return self._calcular({i: max(n, self.tope) for i, n in self.base.items()})

    def minimo_absoluto(self) -> ResultadoCronograma:
        """Lo más corto que podría durar la obra con TODO en paralelo y el tope de personas en cada actividad."""
        p2 = replace(self.p, secuencia="todo_en_paralelo")
        return calcular([replace(a, personas=max(a.personas, self.tope)) for a in self.acts], self.orden, p2, self.hitos)

    def alternativas_frentes(self, max_frentes: Optional[int] = None, limite: int = 8) -> list[Escenario]:
        """Planes que cumplen el plazo abriendo frentes: desde el MENOR número de frentes que alcanza y con los siguientes.

        Más frentes suele pedir MENOS personal total (cada actividad se redondea a días enteros: una cuadrilla que pasa por
        pocos ítems pierde menos), a costa de manejar más frentes a la vez. Se devuelven hasta `limite` planes, de menos a más."""
        if self.plazo.maximo is None:
            raise ValueError("Indica el plazo máximo para abrir frentes de trabajo.")
        tope_k = max(1, min(len(self.acts), max_frentes or len(self.acts)))
        out: list[Escenario] = []
        for k in range(1, tope_k + 1):
            o = self.con_frentes(k)
            if not self._cumple(o._minimo_con_tope()):
                continue  # ni con el tope de gente en cada actividad entra: faltan frentes
            e = o.cumplir_plazo()
            if self._cumple(e.resultado):
                out.append(e)
                if len(out) >= limite:
                    break
        return out

    def abrir_frentes(self, max_frentes: Optional[int] = None) -> Optional[Escenario]:
        """El plan con el menor número de frentes que alcanza el plazo (None si ni con todos los frentes posibles)."""
        alt = self.alternativas_frentes(max_frentes, limite=1)
        return alt[0] if alt else None

    def mas_rapido(self) -> Escenario:
        personas = dict(self.base)
        res = self._calcular(personas)
        mejor = res.dias_habiles
        for _ in range(_MAX_PASOS):
            cands = self._candidatos(res, personas)
            if not cands:
                break
            prueba = dict(personas)
            for c, n, _ahorro in cands:  # todas las actividades críticas a la vez: con caminos críticos en paralelo hace falta
                prueba[c.actividad.id] = n
            nuevo = self._calcular(prueba)
            if nuevo.dias_habiles >= mejor and dias_calendario(nuevo, self.p.fecha_inicio) >= dias_calendario(res, self.p.fecha_inicio):
                break
            personas, res, mejor = prueba, nuevo, nuevo.dias_habiles
        return self._escenario("mas_rapido", personas, res)

    def menor_costo(self) -> Escenario:
        """Parte del plan manual y va sumando personas; se queda con el punto de menor costo total."""
        personas = dict(self.base)
        res = self._calcular(personas)
        mejor = self._escenario("menor_costo", personas, res)
        if self.costos.indirecto_dia <= 0:
            return mejor
        sin_mejora = 0
        for _ in range(_MAX_PASOS):
            cands = self._candidatos(res, personas)
            if not cands:
                break
            c, n, _ahorro = max(cands, key=lambda t: (t[2] / (t[1] - personas[t[0].actividad.id]), t[2]))
            personas[c.actividad.id] = n
            res = self._calcular(personas)
            actual = self._escenario("menor_costo", personas, res)
            if actual.costo_total < mejor.costo_total:
                mejor, sin_mejora = actual, 0
            else:
                sin_mejora += 1
                if sin_mejora >= 25:  # un camino crítico paralelo puede exigir varios pasos antes de ahorrar días
                    break
        return mejor
