import { Fragment, useMemo, useRef, useState } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { BibliotecaOut, ModoRecursos, ProyectoOut, ModeloCostos } from '../types';
import { CeldaPrecio } from './CeldaPrecio';
import { ModeloProyecto } from './ModeloProyecto';
import { Cronograma } from './Cronograma';
import { DetalleItem } from './DetalleItem';

const TIPO_RECURSO = { material: 'Material', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bs = (v: string | null) => (v == null ? '—' : formato.format(Number(v)));
const ROTULO = { error: 'Error', advertencia: 'Advertencia', info: 'Información' } as const;
const ORIGEN_ALERTA = { b1: '', especificaciones: ' (especificaciones)', apu: ' (APU)' } as const;
const MODOS: { valor: ModoRecursos; titulo: string; ayuda: string }[] = [
  { valor: 'hibrido', titulo: 'Híbrido', ayuda: 'Los recursos de tu APU más lo que el pliego pide y falta.' },
  { valor: 'biblioteca', titulo: 'Solo mi biblioteca', ayuda: 'Tu APU tal cual; te aviso si falta algo del pliego.' },
  { valor: 'pliego', titulo: 'Solo el pliego', ayuda: 'Únicamente los recursos que pide la especificación.' },
];

interface Props {
  proyecto: ProyectoOut;
  bibliotecas: BibliotecaOut[];
  modelos: ModeloCostos[];
  onModelosCambiaron: () => void;
  onActualizar: (p: ProyectoOut) => void;
  onBorrar: () => void;
}

export function ProyectoVista({ proyecto, bibliotecas, modelos, onModelosCambiaron, onActualizar, onBorrar }: Props) {
  const [busqueda, setBusqueda] = useState('');
  const [cerrados, setCerrados] = useState<Set<number>>(new Set());
  const [abiertos, setAbiertos] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [modo, setModo] = useState<ModoRecursos>(proyecto.modo_recursos);
  const [bibliotecaSel, setBibliotecaSel] = useState<number | 'todas'>('todas');
  const entradaEsp = useRef<HTMLInputElement>(null);

  const bibliotecaIds = bibliotecaSel === 'todas' ? bibliotecas.map((b) => b.id) : [bibliotecaSel];

  // Las alertas de nivel "información" no marcan la fila; las demás sí.
  const avisosPorItem = useMemo(() => {
    const m = new Map<number, { texto: string; error: boolean }[]>();
    for (const a of proyecto.alertas) {
      if (a.item_numero == null || a.nivel === 'info') continue;
      m.set(a.item_numero, [...(m.get(a.item_numero) ?? []), { texto: a.mensaje, error: a.nivel === 'error' }]);
    }
    return m;
  }, [proyecto.alertas]);

  async function ejecutar(accion: () => Promise<void>) {
    try {
      setError('');
      setInfo('');
      setOcupado(true);
      await accion();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  async function fijarPrecio(itemId: number, valor: string | null) {
    try {
      setError('');
      onActualizar(await api.fijarPrecio(itemId, valor));
    } catch (e) {
      setError(mensajeDe(e));
      throw e;
    }
  }

  async function fijarPrecioRecurso(clave: string, valor: string | null) {
    try {
      setError('');
      onActualizar(await api.fijarPrecioRecurso(proyecto.id, clave, valor));
    } catch (e) {
      setError(mensajeDe(e));
      throw e;
    }
  }

  const descargarExcel = () =>
    ejecutar(async () => {
      descargar(await api.exportar(proyecto.id, null), nombreArchivo(`presupuesto-${proyecto.nombre}`, 'xlsx'));
    });

  const subirEspecificaciones = (archivo: File) =>
    ejecutar(async () => onActualizar(await api.importarEspecificaciones(proyecto.id, archivo)));

  const vincularAuto = () =>
    ejecutar(async () => {
      const r = await api.vincularAuto(proyecto.id, { modo, biblioteca_ids: bibliotecaIds.length ? bibliotecaIds : null });
      onActualizar(r.proyecto);
      setInfo(
        `Vinculados con confianza alta: ${r.vinculados}` +
          (r.solo_pliego ? ` · solo con el pliego: ${r.solo_pliego}` : '') +
          ` · por revisar: ${r.por_revisar} · sin candidato: ${r.sin_candidato}.`,
      );
    });

  function alternar(conjunto: Set<number>, poner: (s: Set<number>) => void, id: number) {
    const nuevo = new Set(conjunto);
    if (!nuevo.delete(id)) nuevo.add(id);
    poner(nuevo);
  }

  const q = busqueda.trim().toLowerCase();

  return (
    <section>
      <header className="cabecera">
        <div>
          <h2>{proyecto.nombre}</h2>
          <p className="tenue">
            {proyecto.total_items} ítems en {proyecto.modulos.length} módulos · {proyecto.items_con_especificacion} con
            especificación · {proyecto.items_con_apu} con APU · {proyecto.items_con_precio} con precio
            {proyecto.archivo_b1 ? ` · ${proyecto.archivo_b1}` : ''}
          </p>
        </div>
        <div className="total-proyecto">
          <span className="tenue">Total del proyecto</span>
          <strong>Bs {bs(proyecto.total)}</strong>
        </div>
      </header>

      {error && <p className="mensaje error" role="alert">{error}</p>}
      {info && <p className="mensaje" role="status">{info}</p>}

      <ul className="alertas">
        {proyecto.alertas.length === 0 ? (
          <li><b className="ok">Sin alertas.</b> Las dos lecturas del PDF coinciden.</li>
        ) : (
          proyecto.alertas.map((a) => (
            <li key={a.id} className={a.nivel}>
              <b>{ROTULO[a.nivel]}{ORIGEN_ALERTA[a.origen]}:</b> {a.mensaje}
            </li>
          ))
        )}
      </ul>

      <fieldset className="panel-vinculo" disabled={ocupado}>
        <legend>Armar los APU con tu biblioteca</legend>
        <div className="modos" role="radiogroup" aria-label="Recursos del APU">
          {MODOS.map((m) => (
            <label key={m.valor} className={modo === m.valor ? 'modo activo' : 'modo'}>
              <input type="radio" name="modo" value={m.valor} checked={modo === m.valor} onChange={() => setModo(m.valor)} />
              <span><strong>{m.titulo}</strong><span className="tenue">{m.ayuda}</span></span>
            </label>
          ))}
        </div>
        <div className="acciones">
          <label className="campo">
            Biblioteca
            <select value={bibliotecaSel} onChange={(e) => setBibliotecaSel(e.target.value === 'todas' ? 'todas' : Number(e.target.value))}>
              <option value="todas">Todas</option>
              {bibliotecas.map((b) => <option key={b.id} value={b.id}>{b.nombre}</option>)}
            </select>
          </label>
          <button type="button" className="boton primario" onClick={() => void vincularAuto()}
                  disabled={modo !== 'pliego' && bibliotecas.length === 0}>
            Vincular automáticamente
          </button>
        </div>
        <p className="tenue nota">
          Solo se aplican las coincidencias de confianza alta con la misma unidad del B-1. Lo demás lo eliges ítem por
          ítem en «Ver detalle». Un APU con líneas pendientes no da precio hasta completarse.
        </p>
      </fieldset>

      <ModeloProyecto proyecto={proyecto} modelos={modelos} onActualizar={onActualizar} onModelosCambiaron={onModelosCambiaron} />

      {proyecto.recursos.length > 0 && (
        <details className="panel-recursos">
          <summary>
            Precios de los recursos del proyecto ({proyecto.recursos.length} recursos
            {proyecto.recursos.some((r) => r.estado !== 'completo')
              ? ` · ${proyecto.recursos.filter((r) => r.estado !== 'completo').length} sin precio completo`
              : ''}
            )
          </summary>
          <p className="tenue nota">
            Cada recurso se usa en varios ítems. Escribe su precio aquí una sola vez y se aplica en todos los APU del
            proyecto donde aparezca.
          </p>
          <div className="tabla-caja">
            <table className="tabla-apu">
              <thead>
                <tr><th>Tipo</th><th>Recurso</th><th>Unidad</th><th className="num">Usado en</th><th className="num">Precio (Bs)</th></tr>
              </thead>
              <tbody>
                {proyecto.recursos.map((r) => (
                  <tr key={r.clave} className={r.estado === 'completo' ? '' : 'pendiente'}>
                    <td>{TIPO_RECURSO[r.tipo]}</td>
                    <td>{r.nombre}</td>
                    <td>{r.unidad || '—'}</td>
                    <td className="num">{r.usos} {r.usos === 1 ? 'ítem' : 'ítems'}</td>
                    <td className="num">
                      <CeldaPrecio valor={r.precio} grupo="recurso" ancho={104} etiqueta={`Precio de ${r.nombre}`}
                                   onGuardar={(v) => fijarPrecioRecurso(r.clave, v)} />
                      {r.estado === 'varios' && <div className="tenue">precios distintos o incompletos</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <details className="panel-recursos">
        <summary>Cronograma de ejecución (con hitos por módulo)</summary>
        <Cronograma proyecto={proyecto} />
      </details>

      <div className="barra">
        <input
          type="search"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscar por número o descripción"
          aria-label="Buscar ítems"
        />
        <div className="acciones">
          <button type="button" className="boton" disabled={ocupado} onClick={() => entradaEsp.current?.click()}>
            {proyecto.items_con_especificacion ? 'Reemplazar especificaciones (PDF)' : 'Importar especificaciones (PDF)'}
          </button>
          <input
            ref={entradaEsp}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void subirEspecificaciones(f);
              e.target.value = '';
            }}
          />
          <button type="button" className="boton" disabled={ocupado} onClick={() => void descargarExcel()}>Descargar Excel</button>
          <button type="button" className="boton peligro" onClick={onBorrar}>Eliminar proyecto</button>
        </div>
      </div>

      <div className="tabla-caja">
        <table>
          <thead>
            <tr>
              <th className="num">N°</th>
              <th>Descripción</th>
              <th>Unidad</th>
              <th className="num">Cantidad</th>
              <th className="num">Precio unitario</th>
              <th className="num">Total (Bs)</th>
            </tr>
          </thead>
          <tbody>
            {proyecto.modulos.map((m) => {
              const items = m.items.filter((it) => !q || String(it.numero) === q || it.descripcion.toLowerCase().includes(q));
              if (q && items.length === 0) return null;
              const cerrado = !q && cerrados.has(m.id);
              return (
                <Fragment key={m.id}>
                  <tr className="modulo">
                    <td colSpan={6}>
                      <button type="button" aria-expanded={!cerrado} onClick={() => alternar(cerrados, setCerrados, m.id)}>
                        <span>{cerrado ? '▸' : '▾'} {m.codigo || '—'}</span>
                        <span>{m.nombre}</span>
                        <span className="resumen-modulo">{m.items_con_precio}/{m.items.length} con precio · Bs {bs(m.total)}</span>
                      </button>
                    </td>
                  </tr>
                  {!cerrado &&
                    items.map((it) => {
                      const avisos = avisosPorItem.get(it.numero);
                      const clase = avisos ? (avisos.some((a) => a.error) ? 'marcado error' : 'marcado') : '';
                      const abierto = abiertos.has(it.id);
                      return (
                        <Fragment key={it.id}>
                          <tr className={clase} title={avisos?.map((a) => a.texto).join('\n')}>
                            <td className="num tenue">{it.numero}</td>
                            <td>
                              {it.descripcion}
                              {it.apu && (
                                <span className={`chip ${it.apu.estado}`}> APU {it.apu.estado}
                                  {it.vinculo_confianza && !it.vinculo_confirmado ? ` · auto (${it.vinculo_confianza})` : ''}
                                </span>
                              )}
                              <button type="button" className="enlace" aria-expanded={abierto}
                                      onClick={() => alternar(abiertos, setAbiertos, it.id)}>
                                {abierto ? 'Ocultar' : 'Ver'} detalle
                                {it.tiene_especificacion ? ` (${it.requisitos.length} ${it.requisitos.length === 1 ? 'recurso' : 'recursos'} del pliego)` : ''}
                              </button>
                            </td>
                            <td title={it.unidad !== it.unidad_normalizada ? `Se compara como: ${it.unidad_normalizada}` : undefined}>
                              {it.unidad}
                            </td>
                            <td className="num">{it.cantidad_texto}</td>
                            <td className="num">
                              {it.modo_precio === 'apu' ? (
                                <span title={it.precio_unitario == null ? 'El APU tiene líneas pendientes' : 'Calculado con el APU'}>
                                  {bs(it.precio_unitario)}
                                </span>
                              ) : (
                                <CeldaPrecio valor={it.precio_unitario} onGuardar={(v) => fijarPrecio(it.id, v)} />
                              )}
                            </td>
                            <td className="num">{bs(it.total)}</td>
                          </tr>
                          {abierto && (
                            <tr className="detalle">
                              <td colSpan={6}>
                                <DetalleItem item={it} modo={modo} bibliotecaIds={bibliotecaIds} onActualizar={onActualizar} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
