from datetime import date
from decimal import Decimal

from ..cronograma import Parametros, actividades_del_proyecto, calcular
from ..db.models import Proyecto
from ..schemas import ActividadCronoOut, CronogramaIn, CronogramaOut, ModuloCronoOut, SinProgramarOut


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def calcular_cronograma(proyecto: Proyecto, datos: CronogramaIn) -> CronogramaOut:
    """Cronograma a partir de la mano de obra de los APU del proyecto (no se guarda: se calcula al pedirlo)."""
    horas = Decimal(str(datos.horas_jornada))
    actividades, sin = actividades_del_proyecto(proyecto, datos.personas_por_defecto, datos.personas, horas)
    params = Parametros(datos.fecha_inicio, horas, datos.trabaja_sabados, frozenset(datos.feriados), datos.secuencia)
    res = calcular(actividades, [m.id for m in proyecto.modulos], params, hitos=datos.hitos)

    nombre_modulo = {m.id: m for m in proyecto.modulos}
    modulos = [
        ModuloCronoOut(id=m.id, codigo=nombre_modulo[m.id].codigo, nombre=nombre_modulo[m.id].nombre, inicio=m.inicio,
                       fin=m.fin, hito=m.hito, atraso_dias=m.atraso_dias)
        for m in res.modulos
    ]
    avisos = []
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
        actividades=[
            ActividadCronoOut(
                item_id=c.actividad.id, numero=c.actividad.numero, nombre=c.actividad.nombre,
                modulo_id=c.actividad.modulo, modulo_codigo=nombre_modulo[c.actividad.modulo].codigo,
                horas_hombre=f"{c.actividad.horas_hombre:.2f}", personas=c.actividad.personas,
                duracion_dias=c.duracion, inicio=c.inicio, fin=c.fin, holgura_dias=c.holgura, critica=c.critica,
                espera_dias=c.actividad.espera_calendario, nota=c.actividad.nota)
            for c in res.actividades
        ],
        modulos=modulos,
        sin_programar=[SinProgramarOut(item_id=i.id, numero=i.numero, nombre=i.descripcion, motivo=motivo) for i, motivo in sin],
        avisos=avisos,
    )
