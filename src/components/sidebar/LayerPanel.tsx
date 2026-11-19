import type { Category, CategoryId, LayerVisibility } from '../../types';
import { formatNumber } from '../../lib/format';

/** Le voci della sezione "Livelli e colori" (le linee autobus hanno una sezione loro, BusPanel). `minZoom` = sotto questo zoom il livello non si disegna. */
const LAYER_ROWS: { key: keyof LayerVisibility; label: string; minZoom?: 'streets' | 'lotNumbers' }[] = [
  { key: 'satellite', label: 'Satellite' },
  { key: 'quarterTint', label: 'Colori dei quartieri' },
  { key: 'quarterNames', label: 'Nomi dei quartieri' },
  { key: 'streetNames', label: 'Nomi delle vie', minZoom: 'streets' },
  { key: 'lotOutlines', label: 'Contorni dei lotti' },
  { key: 'lotNumbers', label: 'Numeri dei lotti', minZoom: 'lotNumbers' },
];

interface LayerPanelProps {
  layers: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
  scale: number;
  minZoom: { streets: number; lotNumbers: number };
  categories: Category[];
  placeCountByCategory: Record<CategoryId, number>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
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

/** Sezione a scomparsa con i livelli della mappa e la legenda dei colori delle funzioni. */
export default function LayerPanel(props: LayerPanelProps) {
  const { layers, onToggle, scale, minZoom, categories, placeCountByCategory, open, onOpenChange } =
    props;
  return (
    <section className="panel-section">
      <button type="button" className="section-toggle" aria-expanded={open} onClick={() => onOpenChange(!open)}>
        <span className="chevron" aria-hidden="true" />
        Livelli e colori
      </button>
      {open && (
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
          <h2>Funzione degli edifici</h2>
          {categories.map((category) => (
            <div key={category.id} className="row is-static">
              <span className="swatch" style={{ background: category.color }} aria-hidden="true" />
              <span className="row-label">{category.label}</span>
              <span className="row-count">{formatNumber(placeCountByCategory[category.id] ?? 0)}</span>
            </div>
          ))}
          <p className="hint">
            Rotella o pizzico per lo zoom, trascina per spostarti, doppio clic per avvicinarti. Passa il mouse su un edificio
            (sul telefono toccalo) per vedere che cos'è; cliccalo per trovarlo nell'elenco. Nomi delle vie e numeri dei lotti
            compaiono da un certo zoom in poi: finché sono troppo piccoli la loro voce è in grigio.
          </p>
        </div>
      )}
    </section>
  );
}
