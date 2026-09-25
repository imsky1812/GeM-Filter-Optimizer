import { useEffect } from "react";

/**
 * Tracks the pointer as two CSS variables on :root (--mx / --my), which the
 * spotlight layer in index.css reads. Mounted once at the app root so the
 * glow follows the cursor across both the landing and the wizard.
 *
 * Skipped entirely on touch/coarse pointers and under reduced motion, where
 * a cursor-following glow has nothing to follow or isn't wanted.
 */
export default function usePointerSpotlight() {
  useEffect(() => {
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || reduce) return undefined;

    const root = document.documentElement;
    root.dataset.spotlight = "on";

    let raf = 0;
    const onMove = (e) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        root.style.setProperty("--mx", `${(e.clientX / window.innerWidth) * 100}%`);
        root.style.setProperty("--my", `${(e.clientY / window.innerHeight) * 100}%`);
      });
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (raf) cancelAnimationFrame(raf);
      delete root.dataset.spotlight;
    };
  }, []);
}
