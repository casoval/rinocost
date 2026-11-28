import { useRef, useState } from 'react';
import { URL_PLANTILLA } from '../api';
import type { BibliotecaOut } from '../types';

interface Props {
  bibliotecas: BibliotecaOut[];
  onImportar: (archivo: File) => void;
  onBorrar: (b: BibliotecaOut) => void;
  onCrear: (nombre: string) => void;
  onAbrir: (b: BibliotecaOut) => void;
}

export function Bibliotecas({ bibliotecas, onImportar, onBorrar, onCrear, onAbrir }: Props) {
  const entrada = useRef<HTMLInputElement>(null);
  const [nombre, setNombre] = useState('');
  return (
    <section aria-labelledby="t-bib">
      <h2 id="t-bib">Mis bibliotecas</h2>
      <p className="tenue">Cada biblioteca es una base de APU y recursos independiente. Se COPIAN al proyecto: editarlas ahí no las altera.</p>
      <form className="acciones" onSubmit={(e) => { e.preventDefault(); if (nombre.trim()) { onCrear(nombre.trim()); setNombre(''); } }}>
        <input className="campo" aria-label="Nombre de la biblioteca nueva" placeholder="Nombre de tu nueva biblioteca" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        <button type="submit" className="boton primario" disabled={!nombre.trim()}>Crear biblioteca vacía</button>
      </form>
      <p className="acciones">
        <button type="button" className="boton" onClick={() => entrada.current?.click()}>Importar biblioteca (Excel)</button>
        <a className="enlace-simple" href={URL_PLANTILLA}>Descargar plantilla de Excel</a>
      </p>
      <input ref={entrada} type="file" accept=".xlsx,.xlsm" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onImportar(f); e.target.value = ''; }} />
      {bibliotecas.length === 0 ? (
        <p className="tenue">Aún no hay bibliotecas. Carga una para vincular tus APU a los ítems.</p>
      ) : (
        <ul className="lista-tarjetas">
          {bibliotecas.map((b) => (
            <li key={b.id} className="fila-biblioteca">
              <span><strong>{b.nombre}</strong> <span className="tenue">{b.total_apus} ítems · {b.total_lineas} líneas</span></span>
              <button type="button" className="boton chico" onClick={() => onAbrir(b)}>Abrir y editar</button>
              <button type="button" className="quitar" aria-label={`Eliminar la biblioteca ${b.nombre}`} onClick={() => onBorrar(b)}>×</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
