interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onShowAll: () => void;
}

/** I pulsanti in alto a destra: avvicina, allontana, mostra tutta la città. */
export default function ZoomControls({ onZoomIn, onZoomOut, onShowAll }: ZoomControlsProps) {
  return (
    <div className="zoom-controls card">
      <button type="button" onClick={onZoomIn} title="Avvicina" aria-label="Avvicina">
        +
      </button>
      <button type="button" onClick={onZoomOut} title="Allontana" aria-label="Allontana">
        −
      </button>
      <button type="button" className="show-all" onClick={onShowAll} title="Mostra tutta la città">
        Tutto
      </button>
    </div>
  );
}
