from datetime import date
from decimal import Decimal

from ..cronograma import Parametros, actividades_del_proyecto
from ..cronograma.optimizador import Costos, Escenario, Optimizador, Plazo, dias_del_plazo
from ..db.models import Proyecto
from ..schemas import (
    ActividadCronoOut, AlternativaFrentesOut, CronogramaIn, CronogramaOut, EscenarioCronoOut, FrenteCronoOut, ModuloCronoOut, SinProgramarOut,
)

_TITULOS = {
    "manual": "Con las personas indicadas",
    "cumplir_plazo": "Cumplir el plazo: frentes, cuadrillas y personal necesarios",
    "mas_rapido": "Lo más rápido posible",
    "menor_costo": "Menor costo (plazo vs. personas)",
}


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _bs(d: Decimal) -> str:
    return f"{d:.2f}"


def _unidad(tipo: str) -> str:
    return "días calendario" if tipo == "calendario" else "días hábiles"


def _titulo(clave: str, e: Escenario) -> str:
    if clave == "cumplir_plazo" and e.secuencia == "frentes_de_trabajo":
        return f"Cumplir el plazo con {e.frentes} frentes en paralelo"
    return _TITULOS[clave]


def _detalle_frentes(e: Escenario) -> list[FrenteCronoOut]:
    out = []
    for f in range(1, e.frentes + 1):
        cs = sorted((c for c in e.resultado.actividades if c.frente == f), key=lambda c: (c.inicio, c.actividad.numero))
        if not cs:
            continue
        out.append(FrenteCronoOut(
            frente=f, personas=max(c.actividad.personas for c in cs), actividades=len(cs),
            numeros=[c.actividad.numero for c in cs], horas_hombre=f"{sum((c.actividad.horas_hombre for c in cs), Decimal(0)):.2f}",
            dias_habiles=sum(c.duracion for c in cs), inicio=min(c.inicio for c in cs), fin=max(c.fin for c in cs)))
    return out


def calcular_cronograma(proyecto: Proyecto, datos: CronogramaIn) -> CronogramaOut:
    """Cronograma a partir de la mano de obra de los APU del proyecto (no se guarda: se calcula al pedirlo).

    Con plazo máximo y/u objetivo, ajusta la cantidad de personas de las actividades de la ruta crítica."""
    horas = Decimal(str(datos.horas_jornada))
    actividades, sin = actividades_del_proyecto(proyecto, datos.personas_por_defecto, datos.personas, horas)
    params = Parametros(datos.fecha_inicio, horas, datos.trabaja_sabados, frozenset(datos.feriados), datos.secuencia, datos.frentes)
    costos = Costos(Decimal(str(datos.costo_indirecto_dia)), Decimal(str(datos.costo_por_persona)))
    if datos.objetivo == "cumplir_plazo" and datos.plazo_maximo is None:
        raise ValueError("Para «Cumplir el plazo» indica el plazo máximo de la obra.")
    if datos.objetivo == "menor_costo" and costos.indirecto_dia <= 0:
        raise ValueError("Para buscar el menor costo indica el costo indirecto por día de obra (gastos generales diarios).")

    opt = Optimizador(
        actividades, [m.id for m in proyecto.modulos], params, datos.hitos,
        {a.id: a.personas for a in actividades}, datos.max_personas, Plazo(datos.plazo_maximo, datos.tipo_plazo), costos,
    )
    escenarios: dict[str, Escenario] = {"manual": opt.manual()}
    frentes_abiertos = False
    alternativas: list[Escenario] = []
    if actividades:
        escenarios["mas_rapido"] = opt.mas_rapido()
        if datos.plazo_maximo is not None:
            plan = opt.cumplir_plazo()
            cumple_con_secuencia = dias_del_plazo(plan.resultado, datos.fecha_inicio, datos.tipo_plazo) <= datos.plazo_maximo
            quiere_frentes = datos.abrir_frentes and len(actividades) > 1
            if quiere_frentes and (not cumple_con_secuencia or datos.secuencia == "frentes_de_trabajo"):
                alternativas = opt.alternativas_frentes(datos.max_frentes)
                if alternativas and not cumple_con_secuencia:
                    plan, frentes_abiertos = alternativas[0], True
            escenarios["cumplir_plazo"] = plan
        if costos.indirecto_dia > 0:
            escenarios["menor_costo"] = opt.menor_costo()
    elegido = escenarios.get(datos.objetivo, escenarios["manual"])
    res = elegido.resultado
    frentes_abiertos = frentes_abiertos and elegido is escenarios.get("cumplir_plazo")
    if elegido is not escenarios.get("cumplir_plazo"):
        alternativas = []  # solo se ofrecen con el objetivo «cumplir el plazo»
    alt_out = [
        AlternativaFrentesOut(
            frentes=e.frentes, personal_total=e.personal_total, pico_personas=e.pico_personas,
            dias_calendario=e.dias_calendario, dias_habiles=e.dias_habiles, fecha_fin=e.resultado.fecha_fin,
            seleccionado=e.frentes == elegido.frentes and elegido.secuencia == "frentes_de_trabajo")
        for e in alternativas
    ] if len(alternativas) > 1 else []

    def cumple(e: Escenario):
        if datos.plazo_maximo is None or not e.resultado.actividades:
            return None
        return dias_del_plazo(e.resultado, datos.fecha_inicio, datos.tipo_plazo) <= datos.plazo_maximo

    nombre_modulo = {m.id: m for m in proyecto.modulos}
    modulos = [
        ModuloCronoOut(id=m.id, codigo=nombre_modulo[m.id].codigo, nombre=nombre_modulo[m.id].nombre, inicio=m.inicio,
                       fin=m.fin, hito=m.hito, atraso_dias=m.atraso_dias, dias_habiles=m.dias_habiles)
        for m in res.modulos
    ]
    avisos: list[str] = []
    if datos.plazo_maximo is not None and res.actividades:
        unidad = _unidad(datos.tipo_plazo)
        usado = dias_del_plazo(res, datos.fecha_inicio, datos.tipo_plazo)
        if cumple(elegido):
            avisos.append(f"Cumple el plazo: {usado} {unidad} de {datos.plazo_maximo} permitidos.")
        else:
            rapido = escenarios["mas_rapido"]
            minimo = dias_del_plazo(rapido.resultado, datos.fecha_inicio, datos.tipo_plazo)
            if minimo > datos.plazo_maximo:
                absoluto = dias_del_plazo(opt.minimo_absoluto(), datos.fecha_inicio, datos.tipo_plazo)
                if datos.objetivo == "cumplir_plazo" and datos.abrir_frentes and absoluto > datos.plazo_maximo:
                    avisos.append(
                        f"No se alcanza el plazo de {datos.plazo_maximo} {unidad}: aun con todos los ítems en paralelo y hasta "
                        f"{datos.max_personas} personas en cada uno, lo más corto posible es {absoluto} {unidad}. Lo limitan las "
                        "esperas obligatorias del pliego (fraguado, secado) o el tope de personas: amplía el plazo, sube el tope "
                        "o revisa las esperas.")
                elif datos.objetivo == "cumplir_plazo" and datos.abrir_frentes:
                    avisos.append(
                        f"No se alcanza el plazo de {datos.plazo_maximo} {unidad} con los frentes permitidos"
                        f"{f' (máximo {datos.max_frentes})' if datos.max_frentes else ''}: con todo en paralelo sí se podría "
                        f"({absoluto} {unidad}). Sube el máximo de frentes o el tope de personas por actividad.")
                else:
                    avisos.append(
                        f"No se alcanza el plazo de {datos.plazo_maximo} {unidad} con esta secuencia: aun con hasta "
                        f"{datos.max_personas} personas por actividad lo más corto posible es {minimo} {unidad} (hoy {usado}). "
                        + (f"Con todo en paralelo se podría llegar a {absoluto} {unidad}: elige «Cumplir el plazo» con la opción de "
                           "abrir frentes, o cambia la secuencia." if absoluto <= datos.plazo_maximo else
                           "Amplía el plazo, sube el tope de personas o revisa las esperas del pliego."))
            else:
                avisos.append(f"Con este plan la obra dura {usado} {unidad} y el plazo es {datos.plazo_maximo}. "
                              "Elige «Cumplir el plazo» para que se sumen las personas necesarias.")
    detalle = _detalle_frentes(elegido) if elegido.frentes else []
    if frentes_abiertos:
        cuadrillas = ", ".join(f"F{f.frente}: {f.personas}" for f in detalle)
        avisos.append(
            f"Con la secuencia indicada no se llegaba al plazo. Se abrieron {elegido.frentes} frentes de trabajo en paralelo; "
            f"cuadrillas ({cuadrillas}), personal necesario: {elegido.personal_total} personas. Cada frente hace sus ítems "
            "uno tras otro: revisa que no haya dependencias técnicas entre ítems de frentes distintos (p. ej. acabados antes "
            "de la obra gruesa).")
        mejor = min(alt_out, key=lambda a: (a.personal_total, a.frentes), default=None)
        if mejor and mejor.frentes != elegido.frentes and mejor.personal_total < elegido.personal_total * 0.9:
            avisos.append(f"Con {mejor.frentes} frentes bastarían {mejor.personal_total} personas "
                          f"(en vez de {elegido.personal_total}): ver «Alternativas de frentes».")
    elif elegido.personas_agregadas and datos.objetivo != "manual":
        avisos.append(f"Se sumaron {elegido.personas_agregadas} persona(s) en actividades de la ruta crítica "
                      f"(pico de {elegido.pico_personas} personas trabajando el mismo día).")
    for m in modulos:
        if m.atraso_dias and m.fin and m.hito:
            avisos.append(f"El módulo {m.codigo} ({m.nombre}) termina el {_dmy(m.fin)}, {m.atraso_dias} días hábiles "
                          f"después de su hito ({_dmy(m.hito)}). Aumenta las personas de las actividades críticas.")
    if sin:
        avisos.append(f"{len(sin)} ítem(s) no se pudieron programar porque su APU no tiene toda la mano de obra "
                      "con cantidad (ver la lista).")
    if not res.actividades:
        avisos.append("Todavía no hay ítems programables: carga las cantidades de mano de obra en los APU.")

    return CronogramaOut(
        fecha_inicio=datos.fecha_inicio, fecha_fin=res.fecha_fin, dias_habiles=res.dias_habiles,
        dias_calendario=elegido.dias_calendario, plazo_maximo=datos.plazo_maximo, tipo_plazo=datos.tipo_plazo,
        cumple_plazo=cumple(elegido), objetivo=datos.objetivo if datos.objetivo in escenarios else "manual",
        pico_personas=elegido.pico_personas, secuencia_usada=elegido.secuencia, frentes=elegido.frentes,
        frentes_abiertos=frentes_abiertos, personal_total=elegido.personal_total, frentes_detalle=detalle,
        alternativas_frentes=alt_out,
        escenarios=[
            EscenarioCronoOut(
                clave=k, titulo=_titulo(k, e), frentes=e.frentes, personal_total=e.personal_total, dias_calendario=e.dias_calendario, dias_habiles=e.dias_habiles,
                fecha_fin=e.resultado.fecha_fin, pico_personas=e.pico_personas, personas_agregadas=e.personas_agregadas,
                costo_plazo=_bs(e.costo_plazo), costo_movilizacion=_bs(e.costo_movilizacion), costo_total=_bs(e.costo_total),
                cumple_plazo=cumple(e), seleccionado=e is elegido)
            for k, e in escenarios.items()
        ] if res.actividades else [],
        actividades=[
            ActividadCronoOut(
                item_id=c.actividad.id, numero=c.actividad.numero, nombre=c.actividad.nombre,
                modulo_id=c.actividad.modulo, modulo_codigo=nombre_modulo[c.actividad.modulo].codigo,
                horas_hombre=f"{c.actividad.horas_hombre:.2f}", personas=c.actividad.personas,
                duracion_dias=c.duracion, inicio=c.inicio, fin=c.fin, holgura_dias=c.holgura, critica=c.critica,
                espera_dias=c.actividad.espera_calendario, nota=c.actividad.nota, predecesoras=c.predecesoras,
                frente=c.frente)
            for c in res.actividades
        ],
        modulos=modulos,
        sin_programar=[SinProgramarOut(item_id=i.id, numero=i.numero, nombre=i.descripcion, motivo=motivo) for i, motivo in sin],
        avisos=avisos,
    )
