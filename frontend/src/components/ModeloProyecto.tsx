import { useState } from 'react';
import { api, mensajeDe } from '../api';
import type { ModeloCostos, PasoModelo, ProyectoOut } from '../types';

interface Props {
  proyecto: ProyectoOut;
  modelos: ModeloCostos[];
  onActualizar: (p: ProyectoOut) => void;
  onModelosCambiaron: () => void;
}

const copia = (m: ModeloCostos): ModeloCostos => JSON.parse(JSON.stringify(m));
const num = (t: string) => Number(String(t).replace(',', '.'));
const fmt = (t: string) => num(t).toLocaleString('es-BO', { maximumFractionDigits: 2 });

/** Aviso (no bloquea) si el porcentaje queda fuera del rango de referencia del paso. */
function aviso(p: PasoModelo): string {
  if (!p.activo || p.minimo === undefined || p.maximo === undefined) return '';
  const v = num(p.porcentaje);
  if (String(p.porcentaje).trim() === '' || Number.isNaN(v)) return 'Escribe un número: así no se puede guardar.';
  return v < num(p.minimo) || v > num(p.maximo) ? `Fuera del rango de referencia (${fmt(p.minimo)} %–${fmt(p.maximo)} %). Verifica el DBC.` : '';
}

export function ModeloProyecto({ proyecto, modelos, onActualizar, onModelosCambiaron }: Props) {
  const [modelo, setModelo] = useState<ModeloCostos | null>(proyecto.modelo_costos ? copia(proyecto.modelo_costos) : null);
  const [cambiado, setCambiado] = useState(false);
  const [perfilId, setPerfilId] = useState<number | null>(null); // perfil del que se partió (para «Actualizar perfil»)
  const [msg, setMsg] = useState<{ texto: string; error: boolean }>({ texto: '', error: false });

  function elegir(clave: string) {
    const m = modelos.find((x) => x.clave === clave);
    if (!m) return;
    if (cambiado && !window.confirm('Tienes cambios sin guardar. ¿Reemplazarlos por este modelo?')) return;
    setModelo(copia(m)); setCambiado(true); setPerfilId(m.propio ? (m.id ?? null) : null); setMsg({ texto: '', error: false });
  }
  function cambiarPaso(codigo: string, cambios: Partial<PasoModelo>) {
    if (!modelo) return;
    const m = copia(modelo);
    for (const s of m.secciones) for (const p of s.pasos) if (p.codigo === codigo) Object.assign(p, cambios);
    setModelo(m); setCambiado(true);
  }
  async function guardar() {
    if (!modelo) return;
    try {
      onActualizar(await api.fijarModeloCostos(proyecto.id, modelo));
      setCambiado(false);
      setMsg({ texto: 'Modelo guardado: los precios de los ítems con APU se recalcularon.', error: false });
    } catch (e) { setMsg({ texto: mensajeDe(e), error: true }); }
  }
  async function comoPerfil(actualizar: boolean) {
    if (!modelo) return;
    const actual = modelos.find((x) => x.id === perfilId);
    const nombre = actualizar && actual ? actual.nombre : window.prompt('Nombre del perfil (p. ej. «Licitación Potosí»):', '')?.trim();
    if (!nombre) return;
    try {
      if (actualizar && perfilId !== null) await api.actualizarPerfil(perfilId, nombre, modelo);
      else setPerfilId((await api.crearPerfil(nombre, modelo)).id ?? null);
      onModelosCambiaron();
      setMsg({ texto: `Perfil «${nombre}» ${actualizar ? 'actualizado' : 'guardado'}. Ya puedes usarlo en proyectos nuevos.`, error: false });
    } catch (e) { setMsg({ texto: mensajeDe(e), error: true }); }
  }

  const pasos = modelo?.secciones.flatMap((s) => s.pasos) ?? [];
  return (
    <details className="panel-recursos">
      <summary>Modelo de cálculo: {modelo ? modelo.nombre : 'solo costo directo (sin modelo)'}</summary>
      <p className="tenue nota">
        Define cómo se pasa del costo directo al precio unitario. Es una copia para este proyecto: cambiarla no altera los
        modelos base ni tus perfiles. Puedes cambiarla en cualquier momento; los precios se recalculan al guardar.
      </p>
      <label className="campo-linea">Cargar un modelo o perfil:{' '}
        <select value="" onChange={(e) => elegir(e.target.value)}>
          <option value="">— elige —</option>
          {modelos.map((m) => <option key={m.clave} value={m.clave}>{m.propio ? `★ ${m.nombre}` : m.nombre}</option>)}
        </select>
      </label>
      {pasos.length > 0 && (
        <table className="tabla-modelo">
          <thead><tr><th>Incluir</th><th>Concepto</th><th className="num">%</th></tr></thead>
          <tbody>
            {pasos.map((p) => (
              <tr key={p.codigo}>
                <td><input type="checkbox" aria-label={`Incluir ${p.codigo}`} checked={p.activo} onChange={(e) => cambiarPaso(p.codigo, { activo: e.target.checked })} /></td>
                <td>
                  {p.etiqueta.replace('{pct}', fmt(p.porcentaje))}
                  {p.ayuda && <div className="tenue">{p.ayuda}</div>}
                  {aviso(p) && <div className="aviso-rango" role="status">{aviso(p)}</div>}
                </td>
                <td className="num">
                  <input className="pct" inputMode="decimal" aria-label={`Porcentaje de ${p.codigo}`} value={p.porcentaje}
                    onChange={(e) => cambiarPaso(p.codigo, { porcentaje: e.target.value.replace(',', '.') })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {modelo?.nota && <p className="tenue nota">{modelo.nota}</p>}
      <p className="acciones">
        <button type="button" className="boton primario" disabled={!modelo || !cambiado} onClick={() => void guardar()}>Guardar y recalcular</button>
        <button type="button" className="boton" disabled={!modelo} onClick={() => void comoPerfil(false)}>Guardar como perfil…</button>
        {perfilId !== null && <button type="button" className="boton" onClick={() => void comoPerfil(true)}>Actualizar perfil</button>}
      </p>
      {msg.texto && <p className={msg.error ? 'mensaje error' : 'mensaje'} role={msg.error ? 'alert' : 'status'}>{msg.texto}</p>}
    </details>
  );
}
