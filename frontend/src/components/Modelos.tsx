import { api, mensajeDe } from '../api';
import type { ModeloCostos } from '../types';
import { useState } from 'react';

interface Props { modelos: ModeloCostos[]; onCambio: () => void }

export function Modelos({ modelos, onCambio }: Props) {
  const [error, setError] = useState('');
  async function borrar(m: ModeloCostos) {
    if (m.id == null || !window.confirm(`¿Eliminar el perfil «${m.nombre}»? Los proyectos que ya lo usan conservan su copia.`)) return;
    try { await api.borrarPerfil(m.id); onCambio(); } catch (e) { setError(mensajeDe(e)); }
  }
  const tarjeta = (m: ModeloCostos) => (
    <article key={m.clave} className="tarjeta">
      <h3>{m.propio ? '★ ' : ''}{m.nombre}</h3>
      <p className="tenue">{m.descripcion}</p>
      {m.secciones.some((s) => s.pasos.length > 0) && (
        <table className="tabla-modelo">
          <thead><tr><th>Concepto</th><th className="num">%</th></tr></thead>
          <tbody>
            {m.secciones.flatMap((s) => s.pasos).map((p) => (
              <tr key={p.codigo}>
                <td>{p.etiqueta.split(' = ')[0]}{!p.activo && <span className="tenue"> (desactivado)</span>}</td>
                <td className="num">{Number(p.porcentaje).toLocaleString('es-BO')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {m.nota && <p className="tenue nota">{m.nota}</p>}
      {m.propio && <p><button type="button" className="boton peligro" onClick={() => void borrar(m)}>Eliminar perfil</button></p>}
    </article>
  );
  const propios = modelos.filter((m) => m.propio);
  return (
    <section aria-labelledby="t-mod">
      <h2 id="t-mod">Modelos de cálculo</h2>
      <p className="tenue">
        Definen cómo se pasa del costo directo al precio unitario. Eliges uno al importar un proyecto y puedes cambiarlo
        después. Para crear tu propio perfil, abre un proyecto, ajusta el modelo y pulsa «Guardar como perfil».
      </p>
      {error && <p className="mensaje error" role="alert">{error}</p>}
      <h3>Modelos base</h3>
      <div className="lista-tarjetas">{modelos.filter((m) => !m.propio).map(tarjeta)}</div>
      <h3>Mis perfiles</h3>
      {propios.length === 0 ? <p className="tenue">Aún no tienes perfiles guardados.</p> : <div className="lista-tarjetas">{propios.map(tarjeta)}</div>}
    </section>
  );
}
