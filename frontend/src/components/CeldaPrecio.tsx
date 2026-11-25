import { useEffect, useState, type KeyboardEvent } from 'react';

interface Props {
  valor: string | null; // "10.50" tal como lo devuelve la API
  onGuardar: (nuevo: string | null) => Promise<void>;
  etiqueta?: string;
  grupo?: string; // Enter y las flechas arriba/abajo se mueven entre las celdas del mismo grupo
  ancho?: number;
}

const aTexto = (v: string | null) => (v == null ? '' : v.replace('.', ','));

/** Celda numérica editable: guarda al salir o con Enter; Esc deshace. Coma o punto decimal. */
export function CeldaPrecio({ valor, onGuardar, etiqueta = 'Precio unitario en bolivianos', grupo = 'precio', ancho }: Props) {
  const [texto, setTexto] = useState(aTexto(valor));
  useEffect(() => setTexto(aTexto(valor)), [valor]);

  async function guardar() {
    const limpio = texto.trim();
    if (limpio === aTexto(valor)) return;
    try {
      await onGuardar(limpio === '' ? null : limpio);
    } catch {
      setTexto(aTexto(valor)); // el error ya se muestra arriba; se vuelve al valor anterior
    }
  }

  function teclas(e: KeyboardEvent<HTMLInputElement>) {
    const campos = Array.from(document.querySelectorAll<HTMLInputElement>(`input[data-grupo="${grupo}"]`));
    const i = campos.indexOf(e.currentTarget);
    if (e.key === 'Enter' || e.key === 'ArrowDown') {
      e.preventDefault();
      campos[i + 1]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      campos[i - 1]?.focus();
    } else if (e.key === 'Escape') {
      setTexto(aTexto(valor));
      e.currentTarget.blur();
    }
  }

  return (
    <input
      data-grupo={grupo}
      className="precio"
      inputMode="decimal"
      value={texto}
      placeholder="—"
      aria-label={etiqueta}
      style={ancho ? { width: ancho } : undefined}
      onChange={(e) => setTexto(e.target.value)}
      onBlur={guardar}
      onKeyDown={teclas}
      onFocus={(e) => e.currentTarget.select()}
    />
  );
}
