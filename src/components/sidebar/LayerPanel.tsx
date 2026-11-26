import type { LayerVisibility } from '../../types';

/** Le voci della sezione "Livelli e colori" (le linee autobus hanno una sezione loro, BusPanel). `minZoom` = sotto questo zoom il livello non si disegna. */
const LAYER_ROWS: { key: keyof LayerVisibility; label: string; minZoom?: 'streets' | 'lotNumbers' | 'activities' }[] = [
  { key: 'satellite', label: 'Satellite' },
  { key: 'quarterTint', label: 'Colori dei quartieri' },
  { key: 'quarterNames', label: 'Nomi dei quartieri' },
  { key: 'streetNames', label: 'Nomi delle vie', minZoom: 'streets' },
  { key: 'lotOutlines', label: 'Contorni dei lotti' },
  { key: 'lotNumbers', label: 'Numeri dei lotti', minZoom: 'lotNumbers' },
  { key: 'activityOutlines', label: 'Perimetri delle attività', minZoom: 'activities' },
  { key: 'activityLabels', label: 'Etichette delle attività sugli edifici' },
  { key: 'heightLabels', label: 'Altezza sopra gli edifici' },
  { key: 'residentLabels', label: 'Residenti sopra gli edifici' },
  { key: 'jobLabels', label: 'Posti di lavoro sopra gli edifici' },
];

interface LayerPanelProps {
  layers: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
  scale: number;
  minZoom: { streets: number; lotNumbers: number; activities: number };
}

/** Interruttore con casella di spunta: l'input vero è nascosto, si vede il riquadro disegnato. */
export function Toggle({ checked, label, dimmed, onChange }: { checked: boolean; label: string; dimmed?: boolean; onChange: () => void }) {
  return (
    <label className={dimmed ? 'row is-dimmed' : 'row'}>
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span className="checkbox" aria-hidden="true" />
      <span className="row-label">{label}</span>
    </label>
  );
}

/** Sezione sempre visibile con i livelli della mappa e le istruzioni d'uso. */
export default function LayerPanel({ layers, onToggle, scale, minZoom }: LayerPanelProps) {
  return (
    <section className="panel-section">
      <h2 className="section-title">Livelli e colori</h2>
      <div className="section-body">
        {LAYER_ROWS.map((row) => (
          <Toggle
            key={row.key}
            label={row.label}
            checked={layers[row.key]}
            // grigio quando il livello è acceso ma lo zoom è troppo basso per vederlo
            dimmed={layers[row.key] && row.minZoom !== undefined && scale < minZoom[row.minZoom]}
            onChange={() => onToggle(row.key)}
          />
        ))}
      </div>
    </section>
  );
}
