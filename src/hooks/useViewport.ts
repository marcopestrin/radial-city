import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { WorldInfo } from '../types';

/**
 * Zoom e spostamento della mappa.
 *
 * La mappa è disegnata in metri; sullo schermo un punto del mondo (wx, wy) finisce in
 *     schermoX = tx + (wx - world.x) * scale
 *     schermoY = ty + (wy - world.y) * scale
 * dove `scale` sono i pixel per metro e (tx, ty) è dove finisce l'angolo in alto a sinistra della mappa.
 *
 * Gesti supportati: rotella (zoom verso il puntatore), trascinamento, pizzico a due dita,
 * doppio clic (zoom ×2, con Maiusc ×0,5), tasti + - 0.
 */

export interface ViewportState {
  scale: number;
  tx: number;
  ty: number;
}

/** La parte dello schermo libera dalla legenda, dove la mappa va centrata. */
export interface FreeArea {
  x0: number;
  width: number;
  height: number;
}

const MIN_SCALE = 0.05;
const MAX_SCALE = 8;
const FLY_DURATION_MS = 650;

function clampScale(scale: number): number {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
}

/** Accelera e poi rallenta (easeInOutQuad). */
function ease(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

export function useViewport(svgRef: RefObject<SVGSVGElement>, world: WorldInfo | null, getFreeArea: () => FreeArea) {
  const [view, setView] = useState<ViewportState>({ scale: 0.1, tx: 0, ty: 0 });

  // copia "viva" dello stato, letta dai gestori degli eventi senza doverli ricreare
  const viewRef = useRef(view);
  viewRef.current = view;
  const animationRef = useRef<number | null>(null);

  const stopAnimation = () => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
  };

  /** Ingrandisce di `factor` tenendo fermo il punto dello schermo (cx, cy). */
  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    stopAnimation();
    setView((current) => {
      const scale = clampScale(current.scale * factor);
      const k = scale / current.scale;
      return { scale, tx: cx - (cx - current.tx) * k, ty: cy - (cy - current.ty) * k };
    });
  }, []);

  /** Mostra tutta la città nella parte libera dello schermo. */
  const fit = useCallback(() => {
    if (!world) return;
    stopAnimation();
    const area = getFreeArea();
    const padding = 24;
    const scale = Math.min((area.width - 2 * padding) / world.width, (area.height - 2 * padding) / world.height);
    setView({
      scale,
      tx: area.x0 + (area.width - world.width * scale) / 2,
      ty: (area.height - world.height * scale) / 2,
    });
  }, [world, getFreeArea]);

  /** Vola con un'animazione fino a un rettangolo del mondo [minX, minY, maxX, maxY]. */
  const flyTo = useCallback(
    (bbox: [number, number, number, number]) => {
      if (!world) return;
      stopAnimation();
      const area = getFreeArea();
      const boxWidth = Math.max(bbox[2] - bbox[0], 12);
      const boxHeight = Math.max(bbox[3] - bbox[1], 12);
      // il rettangolo occupa circa un quinto della parte libera, senza zoomare troppo
      const targetScale = Math.max(0.8, Math.min((area.width * 0.18) / boxWidth, (area.height * 0.18) / boxHeight, 2.4));
      const targetX = (bbox[0] + bbox[2]) / 2;
      const targetY = (bbox[1] + bbox[3]) / 2;

      const start = viewRef.current;
      const centreX = area.x0 + area.width / 2;
      const centreY = area.height / 2;
      const startX = (centreX - start.tx) / start.scale + world.x;
      const startY = (centreY - start.ty) / start.scale + world.y;
      const startTime = performance.now();

      const step = (now: number) => {
        const t = Math.min(1, (now - startTime) / FLY_DURATION_MS);
        const e = ease(t);
        // la scala si interpola in modo logaritmico: lo zoom sembra uniforme
        const scale = Math.exp(Math.log(start.scale) + (Math.log(targetScale) - Math.log(start.scale)) * e);
        const x = startX + (targetX - startX) * e;
        const y = startY + (targetY - startY) * e;
        setView({ scale, tx: centreX - (x - world.x) * scale, ty: centreY - (y - world.y) * scale });
        animationRef.current = t < 1 ? requestAnimationFrame(step) : null;
      };
      animationRef.current = requestAnimationFrame(step);
    },
    [world, getFreeArea],
  );

  // ---------------------------------------------------------------- gesti
  // Pointer events: un dito o il mouse trascinano, due dita fanno il pizzico.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const lastPinch = useRef<{ distance: number; cx: number; cy: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const localPoint = (event: { clientX: number; clientY: number }) => {
      const rect = svg.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault(); // altrimenti la pagina scorrerebbe
      const unit = event.deltaMode === 1 ? 0.05 : 0.0018; // righe oppure pixel
      const p = localPoint(event);
      zoomAt(Math.exp(-event.deltaY * unit), p.x, p.y);
    };

    const onPointerDown = (event: PointerEvent) => {
      stopAnimation();
      pointers.current.set(event.pointerId, localPoint(event));
      lastPinch.current = null;
      setDragging(true);
      try {
        svg.setPointerCapture(event.pointerId);
      } catch {
        // alcuni browser rifiutano la cattura: il trascinamento funziona lo stesso
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      const previous = pointers.current.get(event.pointerId);
      if (!previous) return;
      const p = localPoint(event);
      pointers.current.set(event.pointerId, p);

      if (pointers.current.size === 1) {
        const dx = p.x - previous.x;
        const dy = p.y - previous.y;
        setView((current) => ({ ...current, tx: current.tx + dx, ty: current.ty + dy }));
        return;
      }
      // pizzico: zoom secondo la distanza tra le due dita, spostamento secondo il loro punto medio
      const [a, b] = [...pointers.current.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      const cx = (a.x + b.x) / 2;
      const cy = (a.y + b.y) / 2;
      const last = lastPinch.current;
      if (last) {
        setView((current) => {
          const scale = clampScale(current.scale * (distance / last.distance));
          const k = scale / current.scale;
          const tx = cx - (cx - (current.tx + cx - last.cx)) * k;
          const ty = cy - (cy - (current.ty + cy - last.cy)) * k;
          return { scale, tx, ty };
        });
      }
      lastPinch.current = { distance, cx, cy };
    };

    const onPointerUp = (event: PointerEvent) => {
      pointers.current.delete(event.pointerId);
      lastPinch.current = null;
      if (pointers.current.size === 0) setDragging(false);
    };

    const onDoubleClick = (event: MouseEvent) => {
      const p = localPoint(event);
      zoomAt(event.shiftKey ? 0.5 : 2, p.x, p.y);
    };

    svg.addEventListener('wheel', onWheel, { passive: false });
    svg.addEventListener('pointerdown', onPointerDown);
    svg.addEventListener('pointermove', onPointerMove);
    svg.addEventListener('pointerup', onPointerUp);
    svg.addEventListener('pointercancel', onPointerUp);
    svg.addEventListener('dblclick', onDoubleClick);
    return () => {
      svg.removeEventListener('wheel', onWheel);
      svg.removeEventListener('pointerdown', onPointerDown);
      svg.removeEventListener('pointermove', onPointerMove);
      svg.removeEventListener('pointerup', onPointerUp);
      svg.removeEventListener('pointercancel', onPointerUp);
      svg.removeEventListener('dblclick', onDoubleClick);
    };
  }, [svgRef, zoomAt, world]);

  // tastiera: + e - ingrandiscono al centro, 0 mostra tutta la città
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
      const centreX = window.innerWidth / 2;
      const centreY = window.innerHeight / 2;
      if (event.key === '+' || event.key === '=') zoomAt(1.4, centreX, centreY);
      else if (event.key === '-') zoomAt(1 / 1.4, centreX, centreY);
      else if (event.key === '0') fit();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [zoomAt, fit]);

  useEffect(() => stopAnimation, []);

  return { view, dragging, zoomAt, fit, flyTo };
}
