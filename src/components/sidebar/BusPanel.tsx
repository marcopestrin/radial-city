import type { BusLine } from '../../types';
import { formatNumber } from '../../lib/format';
import { Toggle } from './LayerPanel';

interface BusPanelProps {
  visible: boolean; // il livello "Linee autobus" è acceso
  onToggleVisible: () => void;
  lines: BusLine[];
  hiddenLines: string[];
  onToggleLine: (id: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Sezione a scomparsa con le linee degli autobus: un interruttore per tutte e uno per ciascuna linea. */
export default function BusPanel({ visible, onToggleVisible, lines, hiddenLines, onToggleLine, open, onOpenChange }: BusPanelProps) {
  if (lines.length === 0) return null;
  const shown = lines.filter((line) => !hiddenLines.includes(line.id)).length;
  return (
    <section className="panel-section">
      <button type="button" className="section-toggle" aria-expanded={open} onClick={() => onOpenChange(!open)}>
        <span className="chevron" aria-hidden="true" />
        Linee autobus
        <span className="section-count">{visible ? `${shown} di ${lines.length}` : 'spente'}</span>
      </button>
      {open && (
        <div className="section-body">
          <Toggle label="Mostra le linee sulla mappa" checked={visible} onChange={onToggleVisible} />
          <h2>Linee</h2>
          {lines.map((line) => (
            <label key={line.id} className={visible ? 'row bus-row' : 'row bus-row is-dimmed'} title={line.description}>
              <input type="checkbox" checked={!hiddenLines.includes(line.id)} onChange={() => onToggleLine(line.id)} />
              <span className="checkbox" aria-hidden="true" />
              <span className="bus-badge" style={{ background: line.color }} aria-hidden="true">
                {line.short}
              </span>
              <span className="row-label">{line.name}</span>
              <span className="row-count">
                {formatNumber(Math.round(line.lengthM / 100) / 10)} km · {line.stops.length} fermate
              </span>
            </label>
          ))}
        </div>
      )}
    </section>
  );
}
