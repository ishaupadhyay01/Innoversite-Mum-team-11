import { useEffect, useState } from "react";

const NAMES = ["pass", "fail", "na", "warn", "accent", "version", "muted", "faint", "line", "ink", "surface"] as const;
type Name = (typeof NAMES)[number];
export type ChartColors = Record<Name, string>;

function read(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  const out = {} as ChartColors;
  for (const n of NAMES) {
    const triplet = style.getPropertyValue(`--${n}`).trim().split(/\s+/).join(",");
    out[n] = triplet ? `rgb(${triplet})` : "#888";
  }
  return out;
}

/** SVG presentation attributes cannot use CSS variables, so charts read the resolved token colors. */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(read);
  useEffect(() => {
    const observer = new MutationObserver(() => setColors(read()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return colors;
}
