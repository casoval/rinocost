from dataclasses import replace
from datetime import date
from decimal import Decimal

from ..cronograma import FASES, Parametros, actividades_del_proyecto
from ..cronograma.optimizador import Costos, Escenario, Optimizador, Plazo, dias_del_plazo, tope_automatico
from ..db.models import Proyecto
from ..schemas import (
    ActividadCronoOut, CronogramaIn, CronogramaOut, EscenarioCronoOut, FrenteCronoOut, ModuloCronoOut, SinProgramarOut,
)

_TITULOS = {
    "manual": "Manual: con las personas indicadas",
    "cumplir_plazo": "Por tiempo (automático): personas calculadas para cumplir el plazo",
    "mas_rapido": "Por velocidad: lo más rápido posible",
    "menor_costo": "Por costo: el más barato (plazo vs. personas)",
}


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _bs(d: Decimal) -> str:
    return f"{d:.2f}"


def _unidad(tipo: str) -> str:
    return "días calendario" if tipo == "calendario" else "días hábiles"


def _esperas_criticas(res) -> str:
    """Esperas obligatorias del pliego que están en la ruta crítica: no se acortan poniendo más gente."""
    e = [c for c in res.actividades if c.critica and c.actividad.espera_calendario > 0]
    if not e:
        return ""
    lista = ", ".join(f"ítem {c.actividad.numero} ({c.actividad.espera_calendario} días)" for c in e)
    return f" En la ruta crítica hay esperas obligatorias del pliego (fraguado, secado) que no se acortan con más gente: {lista}."


def _titulo(clave: str, e: Escenario) -> str:
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

    Objetivo «cumplir_plazo» = modo AUTOMÁTICO: el programa decide solo las personas de cada actividad y el tope, con la
    lógica constructiva (cada etapa espera a la anterior; las predecesoras se pueden editar). En los demás objetivos se
    respetan las personas y el tope que indica el usuario."""
    horas = Decimal(str(datos.horas_jornada))
    costos = Costos(Decimal(str(datos.costo_indirecto_dia)), Decimal(str(datos.costo_por_persona)))
    auto = datos.objetivo == "cumplir_plazo"
    if auto and datos.plazo_maximo is None:
        raise ValueError("Para «Cumplir el plazo» indica el plazo máximo de la obra.")
    if datos.objetivo == "menor_costo" and costos.indirecto_dia <= 0:
        raise ValueError("Para buscar el menor costo indica el costo indirecto por día de obra (gastos generales diarios).")

    modulos_orden = [m.id for m in proyecto.modulos]
    plazo = Plazo(datos.plazo_maximo, datos.tipo_plazo)
    manuales = {i: list(v) for i, v in datos.predecesoras.items()}
    # Plan del usuario: sus personas, su tope y su secuencia (si la secuencia es la constructiva, con sus predecesoras)
    actividades, sin = actividades_del_proyecto(proyecto, datos.personas_por_defecto, {} if auto else datos.personas, horas)
    params = Parametros(datos.fecha_inicio, horas, datos.trabaja_sabados, frozenset(datos.feriados), datos.secuencia, datos.frentes)
    opt = Optimizador(
        actividades, modulos_orden, params, datos.hitos, {a.id: a.personas for a in actividades}, datos.max_personas,
        plazo, costos, manuales if datos.secuencia == "logica_constructiva" else None,
    )
    escenarios: dict[str, Escenario] = {"manual": opt.manual()}
    tope_auto = tope_automatico(actividades, horas)
    if actividades:
        escenarios["mas_rapido"] = opt.mas_rapido()
        if datos.plazo_maximo is not None:
            # Plan automático: parte de 1 persona por actividad y suma gente solo donde acorta la ruta crítica.
            acts_auto = [replace(a, personas=1) for a in actividades]
            opt_auto = Optimizador(
                acts_auto, modulos_orden, replace(params, secuencia="logica_constructiva"), datos.hitos,
                {a.id: 1 for a in acts_auto}, tope_auto, plazo, costos, manuales)
            escenarios["cumplir_plazo"] = opt_auto.cumplir_plazo()
        if costos.indirecto_dia > 0:
            escenarios["menor_costo"] = opt.menor_costo()
    elegido = escenarios.get(datos.objetivo, escenarios["manual"])
    res = elegido.resultado
    es_auto = elegido is escenarios.get("cumplir_plazo")
    tope_usado = tope_auto if es_auto else datos.max_personas

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
    detalle = _detalle_frentes(elegido) if elegido.frentes else []
    logica = elegido.secuencia == "logica_constructiva"
    if datos.plazo_maximo is not None and res.actividades:
        unidad = _unidad(datos.tipo_plazo)
        usado = dias_del_plazo(res, datos.fecha_inicio, datos.tipo_plazo)
        if cumple(elegido):
            avisos.append(f"Cumple el plazo: {usado} {unidad} de {datos.plazo_maximo} permitidos.")
        elif es_auto:
            minimo = usado  # el plan automático ya lleva a su tope todas las actividades que acortan la ruta crítica
            avisos.append(
                f"No se alcanza el plazo de {datos.plazo_maximo} {unidad}: aun con hasta {tope_auto} personas en cada actividad "
                f"de la ruta crítica, la obra no baja de {minimo} {unidad}.{_esperas_criticas(res)} También la limitan que las "
                "etapas van una tras otra y el tope de cuadrilla. Amplía el plazo, o en la columna «Predecesoras» permite que "
                "más ítems se hagan a la vez.")
        else:
            rapido = escenarios["mas_rapido"]
            minimo = dias_del_plazo(rapido.resultado, datos.fecha_inicio, datos.tipo_plazo)
            auto_e = escenarios.get("cumplir_plazo")
            if auto_e is not None and not cumple(auto_e):
                dias_auto = dias_del_plazo(auto_e.resultado, datos.fecha_inicio, datos.tipo_plazo)
                avisos.append(
                    f"El plazo de {datos.plazo_maximo} {unidad} no se puede cumplir: ni calculando las personas automáticamente "
                    f"(método «Por tiempo») baja de {dias_auto} {unidad}.{_esperas_criticas(auto_e.resultado)} "
                    "Amplía el plazo o revisa las predecesoras.")
            elif minimo > datos.plazo_maximo:
                avisos.append(
                    f"No se alcanza el plazo de {datos.plazo_maximo} {unidad} con esta secuencia: aun con hasta "
                    f"{datos.max_personas} personas por actividad lo más corto posible es {minimo} {unidad} (hoy {usado}). "
                    "Elige el método «Por tiempo» para que el programa calcule las personas, o amplía el plazo.")
            else:
                avisos.append(f"Con este plan la obra dura {usado} {unidad} y el plazo es {datos.plazo_maximo}. "
                              "Elige el método «Por tiempo» para que se calculen las personas necesarias.")
    if es_auto:
        cuadrillas = [c.actividad.personas for c in res.actividades]
        avisos.append(
            f"Cálculo automático: cada actividad lleva entre {min(cuadrillas)} y {max(cuadrillas)} personas (tope automático "
            f"{tope_auto} por actividad); como máximo trabajan {elegido.pico_personas} personas a la vez. Solo se suma gente a "
            "las actividades de la ruta crítica, y se quita la que sobra mientras el plazo se siga cumpliendo.")
    if logica:
        editadas = sum(1 for c in res.actividades if c.predecesora_manual)
        avisos.append(
            "Predecesoras por lógica constructiva: demolición → obra gruesa → instalaciones → revoques, cielos y pisos → "
            "carpintería → pintura → artefactos → limpieza. La etapa de cada ítem se deduce de su nombre; revísala y corrige "
            "las predecesoras que no correspondan"
            + (f" ({editadas} ítem(s) con predecesoras editadas por ti)." if editadas else "."))
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
        automatico=es_auto, max_personas_usado=tope_usado, personal_total=elegido.personal_total, frentes_detalle=detalle,
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
                predecesoras_definidas=c.predecesoras_definidas, predecesora_manual=c.predecesora_manual,
                fase=FASES[c.fase] if c.fase >= 0 else "", frente=c.frente)
            for c in res.actividades
        ],
        modulos=modulos,
        sin_programar=[SinProgramarOut(item_id=i.id, numero=i.numero, nombre=i.descripcion, motivo=motivo) for i, motivo in sin],
        avisos=avisos,
    )
