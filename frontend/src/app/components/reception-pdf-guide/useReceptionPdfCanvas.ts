import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';

type Bounds = {
  width: number;
  height: number;
};

/** flex 子で contentRect.height が 0 のとき client から内側の描画域を拾う */
function measurePdfWrapContent(
  el: HTMLDivElement,
  entry?: ResizeObserverEntry,
): Bounds {
  const cs = getComputedStyle(el);
  const pl = parseFloat(cs.paddingLeft) || 0;
  const pr = parseFloat(cs.paddingRight) || 0;
  const pt = parseFloat(cs.paddingTop) || 0;
  const pb = parseFloat(cs.paddingBottom) || 0;
  const clientInnerW = Math.max(0, el.clientWidth - pl - pr);
  const clientInnerH = Math.max(0, el.clientHeight - pt - pb);

  let width = entry?.contentRect.width ?? 0;
  let height = entry?.contentRect.height ?? 0;

  if (width <= 0 && clientInnerW > 0) {
    width = clientInnerW;
  }
  if (height <= 0 && clientInnerH > 0) {
    height = clientInnerH;
  }
  if (width > 0 && height === 0 && clientInnerH > 0) {
    height = clientInnerH;
  }
  if (height > 0 && width === 0 && clientInnerW > 0) {
    width = clientInnerW;
  }
  return { width, height };
}

export function useReceptionPdfCanvas(pdfUrl: string, landscapeReady: boolean) {
  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [containerBounds, setContainerBounds] = useState<Bounds>({ width: 800, height: 600 });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  useLayoutEffect(() => {
    if (isLoading || error) {
      return;
    }
    const el = wrapRef.current;
    if (!el) {
      return;
    }
    const measured = measurePdfWrapContent(el);
    if (measured.width > 0) {
      setContainerBounds({ width: measured.width, height: measured.height });
    }
  }, [isLoading, error, landscapeReady]);

  useEffect(() => {
    if (isLoading || error) {
      return;
    }
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') {
      return;
    }
    const apply = (entry?: ResizeObserverEntry) => {
      const measured = measurePdfWrapContent(el, entry);
      if (measured.width <= 0) {
        return;
      }
      setContainerBounds({ width: measured.width, height: measured.height });
      if (measured.height <= 0) {
        requestAnimationFrame(() => {
          if (wrapRef.current !== el) {
            return;
          }
          const again = measurePdfWrapContent(el);
          if (again.width > 0 && again.height > 0) {
            setContainerBounds(again);
          }
        });
      }
    };
    apply();
    const ro = new ResizeObserver((entries) => {
      apply(entries[0]);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [isLoading, error, landscapeReady]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = '/assets/js/pdf.worker.min.mjs';
        const pdf = await pdfjs.getDocument({ url: pdfUrl }).promise;
        if (cancelled) {
          await pdf.destroy().catch(() => {});
          return;
        }
        if (pdfDocRef.current) {
          await pdfDocRef.current.destroy().catch(() => {});
        }
        pdfDocRef.current = pdf;
        setTotalPages(pdf.numPages);
        setCurrentPage(1);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'PDF を開けませんでした');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      if (pdfDocRef.current) {
        void pdfDocRef.current.destroy();
        pdfDocRef.current = null;
      }
    };
  }, [pdfUrl]);

  useEffect(() => {
    const pdf = pdfDocRef.current;
    const canvas = canvasRef.current;
    if (!pdf || !canvas || currentPage < 1 || currentPage > totalPages) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        renderTaskRef.current?.cancel();
        const page = await pdf.getPage(currentPage);
        if (cancelled) {
          return;
        }
        const viewport0 = page.getViewport({ scale: 1 });
        const { width: cw, height: ch } = containerBounds;
        const scaleByWidth = cw / viewport0.width;
        const scaleByHeight = ch > 0 ? ch / viewport0.height : scaleByWidth;
        const fitScale = Math.min(scaleByWidth, scaleByHeight);
        const scale = Math.min(Math.max(fitScale, 0.2), 3);
        const viewport = page.getViewport({ scale });
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          return;
        }
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const task = page.render({ canvasContext: ctx, viewport });
        renderTaskRef.current = task;
        await task.promise;
      } catch (e) {
        const name = (e as Error)?.name ?? '';
        if (!cancelled && name !== 'RenderingCancelledException' && name !== 'AbortException') {
          console.warn('[ReceptionPdfGuide] render failed:', e);
        }
      }
    })();
    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
    };
  }, [currentPage, totalPages, containerBounds]);

  return {
    canvasRef,
    wrapRef,
    totalPages,
    currentPage,
    setCurrentPage,
    error,
    setError,
    isLoading,
  };
}
