import { useState, type ReactNode } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { ActividadCronoOut, CronogramaIn, CronogramaOut, ObjetivoCrono, ProyectoOut, Secuencia, TipoPlazo } from '../types';
import './cronograma.css';

const SECUENCIAS: { valor: Secuencia; titulo: string }[] = [
  { valor: 'logica_constructiva', titulo: 'Lógica constructiva (cada etapa espera a la anterior; predecesoras editables)' },
  { valor: 'modulos_en_serie', titulo: 'Un módulo tras otro (los ítems de cada módulo, en paralelo)' },
  { valor: 'todo_en_serie', titulo: 'Todos los ítems uno tras otro' },
  { valor: 'todo_en_paralelo', titulo: 'Todo en paralelo' },
  { valor: 'frentes_de_trabajo', titulo: 'Frentes de trabajo (cada frente hace sus ítems en orden)' },
];

/** Cada método de cálculo dice qué indicas tú, qué calcula el programa y qué no se usa. */
type Quien = 'tu' | 'auto' | 'no';
interface Metodo {
  valor: ObjetivoCrono; titulo: string; para: string;
  plazo: 'requerido' | 'opcional'; personas: Quien; tope: Quien; secuencia: Quien; costos: 'requerido' | 'opcional';
}
const METODOS: Metodo[] = [
  { valor: 'cumplir_plazo', titulo: 'Por tiempo', para: 'Tú pones el plazo y el programa calcula cuántas personas lleva cada actividad para cumplirlo.',
    plazo: 'requerido', personas: 'auto', tope: 'auto', secuencia: 'auto', costos: 'opcional' },
  { valor: 'menor_costo', titulo: 'Por costo', para: 'Busca el plan más barato: suma gente mientras lo que ahorras por terminar antes supere lo que cuesta sumarla.',
    plazo: 'opcional', personas: 'tu', tope: 'tu', secuencia: 'tu', costos: 'requerido' },
  { valor: 'mas_rapido', titulo: 'Por velocidad', para: 'Acelera la ruta crítica hasta el tope de personas por actividad: lo más corto posible, y lo que más gente pide.',
    plazo: 'opcional', personas: 'tu', tope: 'tu', secuencia: 'tu', costos: 'opcional' },
  { valor: 'manual', titulo: 'Manual', para: 'No se optimiza nada: la obra dura lo que resulte con las personas que tú pones en cada actividad.',
    plazo: 'opcional', personas: 'tu', tope: 'no', secuencia: 'tu', costos: 'opcional' },
];

function repartoDe(m: Metodo): { tu: string[]; auto: string[]; no: string[] } {
  const r = { tu: [] as string[], auto: [] as string[], no: [] as string[] };
  r.tu.push(m.plazo === 'requerido' ? 'Plazo máximo (obligatorio)' : 'Plazo máximo (opcional: solo avisa si se cumple)');
  const campos: [string, Quien][] = [['Personas por actividad', m.personas], ['Máx. personas por actividad', m.tope], ['Secuencia', m.secuencia]];
  for (const [nombre, q] of campos) r[q].push(nombre);
  if (m.secuencia === 'auto') r.auto.push('Predecesoras (propuestas; las puedes editar en la tabla)');
  r.tu.push(m.costos === 'requerido' ? 'Costo por día de obra (obligatorio)' : 'Costos (opcional: para comparar el costo)');
  return r;
}

const dmy = (s: string | null) => (s ? s.split('-').reverse().join('/') : '—');
const ms = (s: string) => Date.parse(`${s}T00:00:00Z`);
const dias = (a: string, b: string) => Math.round((ms(b) - ms(a)) / 86400000);
const hoy = () => new Date().toISOString().slice(0, 10);
const numero = (texto: string) => Number(texto.replace(',', '.'));

type Cambios = Partial<{
  personas: Record<number, number>; predecesoras: Record<number, number[]>; hitos: Record<number, string>;
  objetivo: ObjetivoCrono; secuencia: Secuencia; frentes: number;
}>;

const bs = (t: string) => Number(t).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function Cronograma({ proyecto }: { proyecto: ProyectoOut }) {
  const [inicio, setInicio] = useState(hoy());
  const [horas, setHoras] = useState('8');
  const [personasDef, setPersonasDef] = useState('2');
  const [sabados, setSabados] = useState(false);
  const [secuencia, setSecuencia] = useState<Secuencia>('logica_constructiva');
  const [feriados, setFeriados] = useState('');
  const [personas, setPersonas] = useState<Record<number, number>>({});
  const [hitos, setHitos] = useState<Record<number, string>>({});
  const [plazo, setPlazo] = useState('');
  const [tipoPlazo, setTipoPlazo] = useState<TipoPlazo>('calendario');
  const [objetivo, setObjetivo] = useState<ObjetivoCrono>('manual');
  const [maxPersonas, setMaxPersonas] = useState('30');
  const [predecesoras, setPredecesoras] = useState<Record<number, number[]>>({});
  const [frentes, setFrentes] = useState('2');
  const [costoDia, setCostoDia] = useState('');
  const [costoPersona, setCostoPersona] = useState('');
  const [empresa, setEmpresa] = useState('');
  const [resultado, setResultado] = useState<CronogramaOut | null>(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  function cuerpo(cambios?: Cambios): CronogramaIn {
    const h = numero(horas);
    const obj = cambios?.objetivo ?? objetivo;
    const m = METODOS.find((x) => x.valor === obj) ?? METODOS[3];
    const auto = m.personas === 'auto';  // en este método el programa decide las personas y el tope
    const p = auto ? 1 : Math.floor(numero(personasDef));
    if (!inicio) throw new Error('Elige la fecha de inicio.');
    if (!(h > 0 && h <= 24)) throw new Error('Las horas de jornada deben estar entre 1 y 24.');
    if (!(p >= 1)) throw new Error('Las personas por actividad deben ser al menos 1.');
    const hitosUsados = cambios?.hitos ?? hitos;
    const seq = m.secuencia === 'auto' ? 'logica_constructiva' : (cambios?.secuencia ?? secuencia);
    const nFrentes = cambios?.frentes ?? Math.floor(numero(frentes));
    if (seq === 'frentes_de_trabajo' && !(nFrentes >= 1)) throw new Error('El número de frentes debe ser al menos 1.');
    const plazoNum = plazo.trim() === '' ? null : Number(plazo.replace(',', '.'));
    if (plazoNum !== null && !(Number.isInteger(plazoNum) && plazoNum >= 1)) throw new Error('El plazo máximo debe ser un número entero de días (1 o más), o déjalo vacío.');
    const tope = m.tope === 'tu' ? Math.floor(numero(maxPersonas)) : 30;
    if (!(tope >= 1)) throw new Error('El tope de personas por actividad debe ser al menos 1.');
    const cDia = costoDia.trim() === '' ? 0 : numero(costoDia);
    const cPersona = costoPersona.trim() === '' ? 0 : numero(costoPersona);
    if (!(cDia >= 0) || !(cPersona >= 0)) throw new Error('Los costos deben ser números de 0 en adelante.');
    if (m.plazo === 'requerido' && plazoNum === null) throw new Error(`Para el método «${m.titulo}» escribe el plazo máximo de la obra.`);
    if (obj === 'menor_costo' && !(cDia > 0)) throw new Error('Para el método «Por costo» escribe el costo por día de obra (gastos generales diarios).');
    return {
      plazo_maximo: plazoNum,
      tipo_plazo: tipoPlazo,
      objetivo: obj,
      max_personas: tope,
      costo_indirecto_dia: cDia,
      costo_por_persona: cPersona,
      fecha_inicio: inicio,
      horas_jornada: h,
      personas_por_defecto: p,
      trabaja_sabados: sabados,
      feriados: feriados.split(/[\s,;]+/).filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t)),
      secuencia: seq,
      frentes: nFrentes >= 1 ? nFrentes : 1,
      personas: auto ? {} : (cambios?.personas ?? personas),
      predecesoras: seq === 'logica_constructiva' ? (cambios?.predecesoras ?? predecesoras) : {},
      hitos: Object.fromEntries(Object.entries(hitosUsados).filter(([, f]) => f)) as Record<number, string>,
    };
  }

  async function calcular(cambios?: Cambios) {
    try {
      setError('');
      setOcupado(true);
      const nuevo = await api.cronograma(proyecto.id, cuerpo(cambios));
      if (cambios?.objetivo) setObjetivo(cambios.objetivo);
      if (cambios?.secuencia) setSecuencia(cambios.secuencia);
      if (cambios?.frentes) setFrentes(String(cambios.frentes));
      if (cambios?.predecesoras) setPredecesoras(cambios.predecesoras);
      setResultado(nuevo);
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

  async function abrirPdf() {
    try {
      setError('');
      setOcupado(true);
      await api.abrirPdfCronograma(proyecto.id, { ...cuerpo(), empresa: empresa.trim() || null });
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

  /** El usuario escribe N° de ítem («3, 5»); se traducen a ids. Vacío = sin predecesoras. */
  function cambiarPredecesoras(a: ActividadCronoOut, texto: string) {
    if (!resultado) return;
    const porNumero = new Map(resultado.actividades.map((x) => [x.numero, x.item_id]));
    const numeros = texto.split(/[\s,;]+/).filter(Boolean).map(Number);
    const malo = numeros.find((n) => !Number.isInteger(n) || !porNumero.has(n));
    if (malo !== undefined) {
      setError(`«${Number.isNaN(malo) ? texto : malo}» no es un ítem programado. Escribe los N° de ítem separados por coma, por ejemplo: 3, 5.`);
      return;
    }
    const ids = [...new Set(numeros.map((n) => porNumero.get(n)!))].filter((id) => id !== a.item_id);
    const igual = ids.length === a.predecesoras_definidas.length && ids.every((id) => a.predecesoras_definidas.includes(id));
    if (igual) return;
    const nuevo = { ...predecesoras, [a.item_id]: ids };
    void calcular({ predecesoras: nuevo });
  }

  function restaurarPredecesoras(itemId: number) {
    const { [itemId]: _quitada, ...resto } = predecesoras;
    void calcular({ predecesoras: resto });
  }

  function cambiarHito(moduloId: number, valor: string) {
    if ((hitos[moduloId] ?? '') === valor) return;
    const nuevo = { ...hitos, [moduloId]: valor };
    setHitos(nuevo);
    void calcular({ hitos: nuevo });
  }

  const metodo = METODOS.find((x) => x.valor === objetivo) ?? METODOS[3];
  const auto = metodo.personas === 'auto';
  const reparto = repartoDe(metodo);
  const editaPred = resultado?.secuencia_usada === 'logica_constructiva';
  const numeroDe = new Map((resultado?.actividades ?? []).map((x) => [x.item_id, x.numero]));
  const hayEditadas = (resultado?.actividades ?? []).some((x) => x.predecesora_manual);
  const conCostos = numero(costoDia || '0') > 0 || numero(costoPersona || '0') > 0;
  const total = resultado?.fecha_fin ? dias(resultado.fecha_inicio, resultado.fecha_fin) + 1 : 1;
  const escala = resultado?.fecha_fin ? marcasDeMes(resultado.fecha_inicio, resultado.fecha_fin, total) : [];
  const pct = (n: number) => `${Math.min(Math.max(n, 0), 100)}%`;

  return (
    <div className="crono">
      <p className="crono-nota">
        La duración de cada ítem sale de la mano de obra de su APU: horas-hombre ÷ (personas × horas de jornada), en días
        hábiles. Solo se programan los ítems cuyo APU tiene <strong>toda</strong> su mano de obra con cantidad.
      </p>

      <fieldset className="crono-params crono-metodos" disabled={ocupado}>
        <legend>1 · ¿Cómo quieres calcular?</legend>
        {METODOS.map((m) => (
          <label key={m.valor} className={objetivo === m.valor ? 'crono-metodo sel' : 'crono-metodo'}>
            <input type="radio" name="metodo-crono" checked={objetivo === m.valor} onChange={() => setObjetivo(m.valor)} />
            <strong>{m.titulo}</strong>
            <span>{m.para}</span>
          </label>
        ))}
        <div className="crono-reparto crono-ancho-total">
          <div><b>Tú indicas</b><ul>{reparto.tu.map((t) => <li key={t}>{t}</li>)}</ul></div>
          <div><b>Lo calcula el programa</b><ul>{reparto.auto.length ? reparto.auto.map((t) => <li key={t}>{t}</li>) : <li className="tenue">Nada: usa lo que indicas</li>}</ul></div>
          <div><b>No se usa</b><ul>{reparto.no.length ? reparto.no.map((t) => <li key={t}>{t}</li>) : <li className="tenue">—</li>}</ul></div>
        </div>
      </fieldset>

      <fieldset className="crono-params" disabled={ocupado}>
        <legend>2 · Datos del método «{metodo.titulo}»</legend>
        <label className="crono-campo">
          <span>Plazo máximo de la obra <small>({metodo.plazo === 'requerido' ? 'días, obligatorio' : 'días, opcional: solo avisa si cumple'})</small></span>
          <input inputMode="numeric" value={plazo} placeholder="Ej.: 33" onChange={(e) => setPlazo(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Los días del plazo son</span>
          <select value={tipoPlazo} onChange={(e) => setTipoPlazo(e.target.value as TipoPlazo)}>
            <option value="calendario">Días calendario (corridos)</option>
            <option value="habiles">Días hábiles (de trabajo)</option>
          </select>
        </label>
        <label className={metodo.personas === 'auto' ? 'crono-campo bloqueado' : 'crono-campo'}>
          <span>Personas por actividad{metodo.personas === 'auto' && <span className="crono-auto">automático</span>}
            {metodo.personas === 'tu' && metodo.valor !== 'manual' && <small> (punto de partida)</small>}</span>
          <input inputMode="numeric" value={auto ? (resultado?.automatico ? 'calculadas (ver tabla)' : 'se calculan') : personasDef}
                 disabled={auto} readOnly={auto} onChange={(e) => setPersonasDef(e.target.value)} />
        </label>
        {metodo.tope !== 'no' && (
          <label className={metodo.tope === 'auto' ? 'crono-campo bloqueado' : 'crono-campo'}>
            <span>Máx. personas por actividad{metodo.tope === 'auto' && <span className="crono-auto">automático</span>}</span>
            <input inputMode="numeric"
                   value={metodo.tope === 'auto' ? (resultado?.automatico ? String(resultado.max_personas_usado) : 'se calcula') : maxPersonas}
                   disabled={metodo.tope === 'auto'} readOnly={metodo.tope === 'auto'} onChange={(e) => setMaxPersonas(e.target.value)} />
          </label>
        )}
        <label className={metodo.secuencia === 'auto' ? 'crono-campo crono-ancho bloqueado' : 'crono-campo crono-ancho'}>
          <span>Secuencia{metodo.secuencia === 'auto' && <span className="crono-auto">automático: lógica constructiva</span>}</span>
          <select value={metodo.secuencia === 'auto' ? 'logica_constructiva' : secuencia} disabled={metodo.secuencia === 'auto'}
                  onChange={(e) => setSecuencia(e.target.value as Secuencia)}>
            {SECUENCIAS.map((x) => <option key={x.valor} value={x.valor}>{x.titulo}</option>)}
          </select>
        </label>
        {metodo.secuencia === 'tu' && secuencia === 'frentes_de_trabajo' && (
          <label className="crono-campo">
            <span>Número de frentes</span>
            <input inputMode="numeric" value={frentes} onChange={(e) => setFrentes(e.target.value)} />
          </label>
        )}
        {metodo.costos === 'requerido' ? (
          <>
            <label className="crono-campo">
              <span>Costo por día de obra <small>(Bs, gastos generales; obligatorio)</small></span>
              <input inputMode="decimal" value={costoDia} placeholder="Ej.: 1500" onChange={(e) => setCostoDia(e.target.value)} />
            </label>
            <label className="crono-campo">
              <span>Costo por persona adicional <small>(Bs, opcional)</small></span>
              <input inputMode="decimal" value={costoPersona} placeholder="Ej.: 300" onChange={(e) => setCostoPersona(e.target.value)} />
            </label>
          </>
        ) : (
          <details className="crono-ancho-total crono-costos-op">
            <summary>Costos (opcional): para comparar el costo de cada opción</summary>
            <div className="crono-params-int">
              <label className="crono-campo">
                <span>Costo por día de obra <small>(Bs, gastos generales)</small></span>
                <input inputMode="decimal" value={costoDia} placeholder="Ej.: 1500" onChange={(e) => setCostoDia(e.target.value)} />
              </label>
              <label className="crono-campo">
                <span>Costo por persona adicional <small>(Bs)</small></span>
                <input inputMode="decimal" value={costoPersona} placeholder="Ej.: 300" onChange={(e) => setCostoPersona(e.target.value)} />
              </label>
            </div>
          </details>
        )}
      </fieldset>

      <fieldset className="crono-params" disabled={ocupado}>
        <legend>3 · Datos generales de la obra</legend>
        <label className="crono-campo">
          <span>Inicio de obra</span>
          <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Horas de jornada</span>
          <input inputMode="decimal" value={horas} onChange={(e) => setHoras(e.target.value)} />
        </label>
        <label className="crono-campo crono-casilla">
          <input type="checkbox" checked={sabados} onChange={(e) => setSabados(e.target.checked)} />
          <span>Se trabaja los sábados</span>
        </label>
        <label className="crono-campo crono-ancho">
          <span>Feriados <small>(AAAA-MM-DD, separados por coma o espacio)</small></span>
          <input value={feriados} placeholder="2026-12-25, 2027-01-01" onChange={(e) => setFeriados(e.target.value)} />
        </label>
        <label className="crono-campo crono-ancho">
          <span>Contratista <small>(se imprime en el PDF)</small></span>
          <input value={empresa} placeholder="Nombre de tu empresa" onChange={(e) => setEmpresa(e.target.value)} />
        </label>
      </fieldset>

      <div className="crono-acciones">
        <button type="button" className="boton primario" disabled={ocupado} onClick={() => void calcular()}>
          {ocupado ? 'Calculando…' : 'Calcular cronograma'}
        </button>
        {hayEditadas && editaPred && (
          <button type="button" className="boton" disabled={ocupado} onClick={() => void calcular({ predecesoras: {} })}>
            Restaurar predecesoras propuestas
          </button>
        )}
        <button type="button" className="boton" disabled={ocupado} onClick={() => void descargarExcel()}>
          Descargar Excel con cronograma
        </button>
        <button type="button" className="boton" disabled={ocupado} onClick={() => void abrirPdf()}>
          Abrir PDF (diseño Project)
        </button>
      </div>
      {error && <p className="mensaje error" role="alert">{error}</p>}

      {resultado && (
        <>
          {resultado.fecha_fin ? (
            <div className="crono-resumen">
              <div><span>Inicio</span><strong>{dmy(resultado.fecha_inicio)}</strong></div>
              <div><span>Fin</span><strong>{dmy(resultado.fecha_fin)}</strong></div>
              <div><span>Duración</span><strong>{resultado.dias_calendario} días calendario</strong><small>{resultado.dias_habiles} días hábiles</small></div>
              {resultado.frentes > 0 && (
                <div><span>Personal necesario</span><strong>{resultado.personal_total} personas</strong>
                  <small>{resultado.frentes} {resultado.frentes === 1 ? 'frente' : 'frentes'}</small></div>
              )}
              <div><span>Personas a la vez (máx.)</span><strong>{resultado.pico_personas}</strong></div>
              {resultado.automatico && (
                <div><span>Tope por actividad</span><strong>{resultado.max_personas_usado}</strong><small>calculado automáticamente</small></div>
              )}
              <div><span>Actividades</span><strong>{resultado.actividades.length}</strong></div>
              {resultado.plazo_maximo !== null && resultado.cumple_plazo !== null && (
                <div className={resultado.cumple_plazo ? 'crono-plazo bien' : 'crono-plazo mal'}>
                  <span>Plazo máximo</span>
                  <strong>{resultado.cumple_plazo ? 'Cumple' : 'No cumple'}</strong>
                  <small>{resultado.plazo_maximo} {resultado.tipo_plazo === 'habiles' ? 'días hábiles' : 'días calendario'}</small>
                </div>
              )}
            </div>
          ) : (
            <p className="crono-nota">Todavía no hay actividades que programar.</p>
          )}
          {resultado.frentes_detalle.length > 0 && (
            <div className="crono-opciones">
              <h3>Frentes y cuadrillas</h3>
              <div className="crono-caja-chica">
                <table className="crono-tabla-opc">
                  <thead>
                    <tr>
                      <th>Frente</th><th className="c-der">Cuadrilla (personas)</th><th className="c-der">Ítems</th><th>N° de ítems, en orden</th>
                      <th className="c-der">Horas-hombre</th><th className="c-der">Días hábiles</th><th>Inicio</th><th>Fin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.frentes_detalle.map((f) => (
                      <tr key={f.frente}>
                        <td><strong>F{f.frente}</strong></td>
                        <td className="c-der">{f.personas}</td>
                        <td className="c-der">{f.actividades}</td>
                        <td className="crono-lista-num">{f.numeros.join(', ')}</td>
                        <td className="c-der">{Number(f.horas_hombre).toLocaleString('es-BO', { maximumFractionDigits: 0 })}</td>
                        <td className="c-der">{f.dias_habiles}</td>
                        <td>{dmy(f.inicio)}</td>
                        <td>{dmy(f.fin)}</td>
                      </tr>
                    ))}
                    <tr className="sel">
                      <td>Total</td><td className="c-der">{resultado.personal_total}</td>
                      <td className="c-der">{resultado.actividades.length}</td><td colSpan={5}>personas a contratar (una cuadrilla por frente)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="crono-ayuda">Cada frente hace sus ítems uno tras otro; los frentes trabajan a la vez. Revisa que no haya dependencias técnicas entre ítems de frentes distintos.</p>
            </div>
          )}
          {resultado.escenarios.length > 1 && (
            <div className="crono-opciones">
              <h3>Opciones de tiempo{conCostos ? ' y costo' : ''}</h3>
              <div className="crono-caja-chica">
                <table className="crono-tabla-opc">
                  <thead>
                    <tr>
                      <th>Opción</th><th className="c-der">Días calendario</th><th className="c-der">Días hábiles</th><th>Fin</th>
                      <th className="c-der">Personas a la vez</th><th className="c-der">Personal necesario</th>
                      {conCostos && <th className="c-der">Costo plazo + personas (Bs)</th>}
                      {resultado.plazo_maximo !== null && <th>Plazo</th>}
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.escenarios.map((e) => (
                      <tr key={e.clave} className={e.seleccionado ? 'sel' : undefined}>
                        <td>{e.titulo}</td>
                        <td className="c-der">{e.dias_calendario}</td>
                        <td className="c-der">{e.dias_habiles}</td>
                        <td>{dmy(e.fecha_fin)}</td>
                        <td className="c-der">{e.pico_personas}</td>
                        <td className="c-der">{e.personal_total}</td>
                        {conCostos && <td className="c-der">{bs(e.costo_total)}</td>}
                        {resultado.plazo_maximo !== null && (
                          <td>{e.cumple_plazo === null ? '—' : e.cumple_plazo ? <span className="crono-chip bien">cumple</span> : <span className="crono-chip mal">no cumple</span>}</td>
                        )}
                        <td className="c-der">
                          {e.seleccionado
                            ? <span className="tenue">en uso</span>
                            : <button type="button" className="boton" disabled={ocupado} onClick={() => void calcular({ objetivo: e.clave })}>Usar</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {resultado.avisos.length > 0 && (
            <ul className="crono-avisos">
              {resultado.avisos.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          )}

          {resultado.actividades.length > 0 && (
            <>
              <p className="crono-leyenda" aria-hidden="true">
                <span><i className="crono-muestra critica" /> Ruta crítica (sin holgura)</span>
                <span><i className="crono-muestra" /> Con holgura</span>
              </p>
              <div className="crono-caja">
                <table className="crono-tabla">
                  <colgroup>
                    <col style={{ width: 40 }} /><col style={{ width: 220 }} /><col style={{ width: 88 }} />
                    <col style={{ width: 92 }} /><col style={{ width: 62 }} /><col style={{ width: 118 }} /><col style={{ width: 90 }} />
                    <col style={{ width: 90 }} /><col style={{ width: 78 }} /><col />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="c-num">N°</th>
                      <th className="c-act">Actividad</th>
                      <th className="c-der">Personas</th>
                      <th className="c-der">Horas-hombre</th>
                      <th className="c-der">Días háb.</th>
                      <th title={editaPred ? 'N° de los ítems que deben terminar antes. Puedes cambiarlos.' : 'Ítems que fijan el inicio'}>Predecesoras</th>
                      <th>Inicio</th>
                      <th>Fin</th>
                      <th className="c-der">Holgura</th>
                      <th className="c-gantt">
                        <div className="crono-escala" aria-hidden="true">
                          {escala.map((m) => <span key={m.clave} style={{ left: pct(m.izq) }}>{m.texto}</span>)}
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.modulos.map((m) => {
                      const acts = resultado.actividades.filter((a) => a.modulo_id === m.id);
                      if (acts.length === 0) return null;
                      return (
                        <FilasModulo key={m.id}>
                          <tr className="crono-modulo">
                            <td colSpan={10}>
                              <div className="crono-modulo-info">
                                <strong>{m.codigo}</strong> <span>{m.nombre}</span>
                                <span className="tenue"> · {dmy(m.inicio)} – {dmy(m.fin)}</span>
                                <label className="crono-hito">
                                  Hito (fecha límite)
                                  <input type="date" defaultValue={m.hito ?? ''} onBlur={(e) => cambiarHito(m.id, e.target.value)} />
                                </label>
                                {m.atraso_dias > 0 && <span className="crono-chip mal">atraso: {m.atraso_dias} días hábiles</span>}
                                {m.hito && m.atraso_dias === 0 && <span className="crono-chip bien">cumple el hito</span>}
                              </div>
                            </td>
                          </tr>
                          {acts.map((a) => (
                            <tr key={a.item_id} title={a.nota || undefined}>
                              <td className="c-num">{a.numero}</td>
                              <td className="c-act">
                                {a.nombre}
                                {resultado.frentes > 1 && a.frente > 0 && <span className="crono-chip frente"> F{a.frente}</span>}
                                {a.espera_dias > 0 && <span className="crono-chip espera"> espera {a.espera_dias} d</span>}
                                {a.fase && <span className="crono-chip fase">{a.fase}</span>}
                              </td>
                              <td className="c-der">
                                <input className="crono-mini" inputMode="numeric" defaultValue={a.personas}
                                       readOnly={resultado.automatico} disabled={resultado.automatico}
                                       title={resultado.automatico ? 'Calculado automáticamente para cumplir el plazo' : undefined}
                                       aria-label={`Personas en ${a.nombre}`} key={`${a.item_id}-${a.personas}`}
                                       onBlur={(e) => cambiarPersonas(a.item_id, e.target.value)}
                                       onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
                              </td>
                              <td className="c-der">{a.horas_hombre}</td>
                              <td className="c-der">{a.duracion_dias}</td>
                              <td className="crono-celda-pred">
                                {editaPred ? (
                                  <>
                                    <input className={a.predecesora_manual ? 'crono-pred editada' : 'crono-pred'} inputMode="numeric"
                                           style={{ width: a.predecesora_manual ? 'calc(100% - 30px)' : '100%' }}
                                           placeholder="—" aria-label={`Predecesoras de ${a.nombre} (N° de ítem)`}
                                           key={`${a.item_id}-${a.predecesoras_definidas.join('.')}`}
                                           title={a.predecesora_manual ? 'Editadas por ti' : 'Propuestas por la lógica constructiva'}
                                           defaultValue={a.predecesoras_definidas.map((id) => numeroDe.get(id)).join(', ')}
                                           onBlur={(e) => cambiarPredecesoras(a, e.target.value)}
                                           onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
                                    {a.predecesora_manual && (
                                      <button type="button" className="crono-restaurar" title="Volver a la propuesta"
                                              aria-label={`Restaurar predecesoras de ${a.nombre}`} onClick={() => restaurarPredecesoras(a.item_id)}>↺</button>
                                    )}
                                  </>
                                ) : (
                                  <span className="crono-pred-lectura">{a.predecesoras.map((id) => numeroDe.get(id)).join(', ') || '—'}</span>
                                )}
                              </td>
                              <td>{dmy(a.inicio)}</td>
                              <td>{dmy(a.fin)}</td>
                              <td className="c-der">
                                {a.critica ? <span className="crono-chip mal">crítica</span> : `${a.holgura_dias} d`}
                              </td>
                              <td className="c-gantt">
                                {/* La barra se posiciona dentro de esta pista (position: relative), nunca respecto de la página. */}
                                <div className="crono-pista">
                                  <div
                                    className={a.critica ? 'crono-barra critica' : 'crono-barra'}
                                    style={{
                                      left: pct((dias(resultado.fecha_inicio, a.inicio) / total) * 100),
                                      width: pct(Math.min(Math.max(((dias(a.inicio, a.fin) + 1) / total) * 100, 0.8),
                                                          100 - (dias(resultado.fecha_inicio, a.inicio) / total) * 100)),
                                    }}
                                    role="img"
                                    aria-label={`${a.nombre}: del ${dmy(a.inicio)} al ${dmy(a.fin)}`}
                                    title={`${dmy(a.inicio)} – ${dmy(a.fin)}`}
                                  />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </FilasModulo>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {resultado.sin_programar.length > 0 && (
            <details className="crono-sin">
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

/** Marcas de mes para la escala del diagrama: una por cada día 1 dentro del rango (más la fecha de inicio). */
function marcasDeMes(inicio: string, fin: string, total: number): { clave: string; texto: string; izq: number }[] {
  const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const marcas: { clave: string; texto: string; izq: number }[] = [];
  const [a, m] = inicio.split('-').map(Number);
  const ultimo = ms(fin);
  let anio = a;
  let mes = m - 1;
  let primera = true;
  for (let guardia = 0; guardia < 240; guardia++) {
    const iso = primera ? inicio : `${anio}-${String(mes + 1).padStart(2, '0')}-01`;
    if (ms(iso) > ultimo) break;
    const texto = `${MESES[mes]}${primera ? ` ${String(anio).slice(2)}` : ''}`;  // el año solo en la primera marca
    marcas.push({ clave: iso, texto, izq: (dias(inicio, iso) / total) * 100 });
    primera = false;
    mes += 1;
    if (mes > 11) { mes = 0; anio += 1; }
  }
  // si la marca del inicio y la del primer mes quedan casi encimadas, se deja la del mes
  if (marcas.length > 1 && marcas[1].izq - marcas[0].izq < 6) {
    marcas.shift();
    marcas[0].texto = `${marcas[0].texto} ${String(marcas[0].clave.slice(2, 4))}`;
  }
  return marcas;
}

/** Agrupa las filas de un módulo sin agregar elementos al DOM. */
function FilasModulo({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
