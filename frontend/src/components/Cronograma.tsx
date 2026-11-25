import { useState, type ReactNode } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { CronogramaIn, CronogramaOut, ProyectoOut, Secuencia } from '../types';

const SECUENCIAS: { valor: Secuencia; titulo: string }[] = [
  { valor: 'modulos_en_serie', titulo: 'Un módulo tras otro (los ítems de cada módulo, en paralelo)' },
  { valor: 'todo_en_serie', titulo: 'Todos los ítems uno tras otro' },
  { valor: 'todo_en_paralelo', titulo: 'Todo en paralelo' },
];

const dmy = (s: string | null) => (s ? s.split('-').reverse().join('/') : '—');
const ms = (s: string) => Date.parse(`${s}T00:00:00Z`);
const dias = (a: string, b: string) => Math.round((ms(b) - ms(a)) / 86400000);
const hoy = () => new Date().toISOString().slice(0, 10);
const numero = (texto: string) => Number(texto.replace(',', '.'));

type Cambios = Partial<{ personas: Record<number, number>; hitos: Record<number, string> }>;

export function Cronograma({ proyecto }: { proyecto: ProyectoOut }) {
  const [inicio, setInicio] = useState(hoy());
  const [horas, setHoras] = useState('8');
  const [personasDef, setPersonasDef] = useState('2');
  const [sabados, setSabados] = useState(false);
  const [secuencia, setSecuencia] = useState<Secuencia>('modulos_en_serie');
  const [feriados, setFeriados] = useState('');
  const [personas, setPersonas] = useState<Record<number, number>>({});
  const [hitos, setHitos] = useState<Record<number, string>>({});
  const [resultado, setResultado] = useState<CronogramaOut | null>(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  function cuerpo(cambios?: Cambios): CronogramaIn {
    const h = numero(horas);
    const p = Math.floor(numero(personasDef));
    if (!inicio) throw new Error('Elige la fecha de inicio.');
    if (!(h > 0 && h <= 24)) throw new Error('Las horas de jornada deben estar entre 1 y 24.');
    if (!(p >= 1)) throw new Error('Las personas por actividad deben ser al menos 1.');
    const hitosUsados = cambios?.hitos ?? hitos;
    return {
      fecha_inicio: inicio,
      horas_jornada: h,
      personas_por_defecto: p,
      trabaja_sabados: sabados,
      feriados: feriados.split(/[\s,;]+/).filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t)),
      secuencia,
      personas: cambios?.personas ?? personas,
      hitos: Object.fromEntries(Object.entries(hitosUsados).filter(([, f]) => f)) as Record<number, string>,
    };
  }

  async function calcular(cambios?: Cambios) {
    try {
      setError('');
      setOcupado(true);
      setResultado(await api.cronograma(proyecto.id, cuerpo(cambios)));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  async function descargarExcel() {
    try {
      setError('');
      setOcupado(true);
      const blob = await api.exportar(proyecto.id, cuerpo());
      descargar(blob, nombreArchivo(`cronograma-${proyecto.nombre}`, 'xlsx'));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  function cambiarPersonas(itemId: number, texto: string) {
    const n = Math.floor(numero(texto));
    if (!(n >= 1) || personas[itemId] === n) return;
    const nuevo = { ...personas, [itemId]: n };
    setPersonas(nuevo);
    void calcular({ personas: nuevo });
  }

  function cambiarHito(moduloId: number, valor: string) {
    if ((hitos[moduloId] ?? '') === valor) return;
    const nuevo = { ...hitos, [moduloId]: valor };
    setHitos(nuevo);
    void calcular({ hitos: nuevo });
  }

  const total = resultado?.fecha_fin ? dias(resultado.fecha_inicio, resultado.fecha_fin) + 1 : 1;

  return (
    <div className="cronograma">
      <p className="tenue nota">
        La duración de cada ítem sale de la mano de obra de su APU: horas-hombre ÷ (personas × horas de jornada), en días
        hábiles. Solo se programan los ítems cuyo APU tiene <strong>toda</strong> su mano de obra con cantidad.
      </p>
      <fieldset className="parametros" disabled={ocupado}>
        <label className="campo">Inicio
          <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </label>
        <label className="campo">Horas de jornada
          <input className="mini corto" inputMode="decimal" value={horas} onChange={(e) => setHoras(e.target.value)} />
        </label>
        <label className="campo">Personas por actividad
          <input className="mini corto" inputMode="numeric" value={personasDef} onChange={(e) => setPersonasDef(e.target.value)} />
        </label>
        <label className="campo casilla-inline">
          <input type="checkbox" checked={sabados} onChange={(e) => setSabados(e.target.checked)} /> Se trabaja los sábados
        </label>
        <label className="campo">Secuencia
          <select value={secuencia} onChange={(e) => setSecuencia(e.target.value as Secuencia)}>
            {SECUENCIAS.map((s) => <option key={s.valor} value={s.valor}>{s.titulo}</option>)}
          </select>
        </label>
        <label className="campo columna">Feriados (fechas AAAA-MM-DD, separadas por coma o espacio)
          <input value={feriados} placeholder="2026-12-25, 2027-01-01" onChange={(e) => setFeriados(e.target.value)} />
        </label>
      </fieldset>
      <div className="acciones">
        <button type="button" className="boton primario" disabled={ocupado} onClick={() => void calcular()}>
          {ocupado ? 'Calculando…' : 'Calcular cronograma'}
        </button>
        <button type="button" className="boton" disabled={ocupado} onClick={() => void descargarExcel()}>
          Descargar Excel con cronograma
        </button>
      </div>
      {error && <p className="mensaje error" role="alert">{error}</p>}

      {resultado && (
        <>
          <p className="resumen-crono">
            {resultado.fecha_fin
              ? <>Del <strong>{dmy(resultado.fecha_inicio)}</strong> al <strong>{dmy(resultado.fecha_fin)}</strong> · {resultado.dias_habiles} días hábiles · {resultado.actividades.length} actividades</>
              : 'Todavía no hay actividades que programar.'}
          </p>
          {resultado.avisos.length > 0 && (
            <ul className="alertas">
              {resultado.avisos.map((a, i) => <li key={i} className="advertencia">{a}</li>)}
            </ul>
          )}

          {resultado.actividades.length > 0 && (
            <div className="tabla-caja">
              <table className="tabla-apu tabla-crono">
                <thead>
                  <tr>
                    <th className="num">N°</th><th>Actividad</th><th className="num">Personas</th>
                    <th className="num">Horas-hombre</th><th className="num">Días háb.</th><th>Inicio</th><th>Fin</th>
                    <th className="num">Holgura</th><th>Diagrama</th>
                  </tr>
                </thead>
                <tbody>
                  {resultado.modulos.map((m) => {
                    const acts = resultado.actividades.filter((a) => a.modulo_id === m.id);
                    if (acts.length === 0) return null;
                    return (
                      <FilasModulo key={m.id}>
                        <tr className="modulo-crono">
                          <td colSpan={9}>
                            <strong>{m.codigo}</strong> {m.nombre}
                            <span className="tenue"> · {dmy(m.inicio)} – {dmy(m.fin)}</span>
                            <label className="hito">
                              Hito (fecha límite)
                              <input type="date" defaultValue={m.hito ?? ''} onBlur={(e) => cambiarHito(m.id, e.target.value)} />
                            </label>
                            {m.atraso_dias > 0 && <span className="chip baja">atraso: {m.atraso_dias} días hábiles</span>}
                            {m.hito && m.atraso_dias === 0 && <span className="chip alta">cumple el hito</span>}
                          </td>
                        </tr>
                        {acts.map((a) => (
                          <tr key={a.item_id} title={a.nota || undefined}>
                            <td className="num tenue">{a.numero}</td>
                            <td>{a.nombre}{a.espera_dias > 0 && <span className="chip req"> espera {a.espera_dias} d</span>}</td>
                            <td className="num">
                              <input className="mini corto" inputMode="numeric" defaultValue={a.personas}
                                     aria-label={`Personas en ${a.nombre}`} key={`${a.item_id}-${a.personas}`}
                                     onBlur={(e) => cambiarPersonas(a.item_id, e.target.value)}
                                     onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
                            </td>
                            <td className="num">{a.horas_hombre}</td>
                            <td className="num">{a.duracion_dias}</td>
                            <td>{dmy(a.inicio)}</td>
                            <td>{dmy(a.fin)}</td>
                            <td className="num">{a.critica ? <span className="chip baja">crítica</span> : `${a.holgura_dias} d`}</td>
                            <td className="gantt">
                              <div
                                className={a.critica ? 'barra-gantt critica' : 'barra-gantt'}
                                style={{
                                  left: `${(dias(resultado.fecha_inicio, a.inicio) / total) * 100}%`,
                                  width: `${Math.max(((dias(a.inicio, a.fin) + 1) / total) * 100, 1)}%`,
                                }}
                                role="img"
                                aria-label={`${a.nombre}: del ${dmy(a.inicio)} al ${dmy(a.fin)}`}
                              />
                            </td>
                          </tr>
                        ))}
                      </FilasModulo>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {resultado.sin_programar.length > 0 && (
            <details className="sin-programar">
              <summary>{resultado.sin_programar.length} ítems sin programar</summary>
              <ul>
                {resultado.sin_programar.map((s) => (
                  <li key={s.item_id}><strong>Ítem {s.numero}</strong> {s.nombre} — <span className="tenue">{s.motivo}</span></li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}

/** Agrupa las filas de un módulo sin agregar elementos al DOM. */
function FilasModulo({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
