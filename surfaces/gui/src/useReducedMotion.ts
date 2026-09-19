import { useEffect, useState } from "react";

export function useReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(media?.matches ?? false);
    sync();
    media?.addEventListener("change", sync);
    return () => media?.removeEventListener("change", sync);
  }, []);
  return reduced;
}
