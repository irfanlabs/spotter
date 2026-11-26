export type LngLat = [number, number];

/** Decode an encoded polyline (default precision 6) into [lng, lat] pairs (MapLibre order). */
export function decodePolyline(encoded: string, precision = 6): LngLat[] {
  const factor = 10 ** precision;
  const out: LngLat[] = [];
  let index = 0;
  let lat = 0;
  let lon = 0;
  while (index < encoded.length) {
    for (let axis = 0; axis < 2; axis++) {
      let shift = 0;
      let result = 0;
      let byte: number;
      do {
        byte = encoded.charCodeAt(index++) - 63;
        result |= (byte & 0x1f) << shift;
        shift += 5;
      } while (byte >= 0x20 && index < encoded.length + 1);
      const delta = result & 1 ? ~(result >> 1) : result >> 1;
      if (axis === 0) lat += delta;
      else lon += delta;
    }
    out.push([lon / factor, lat / factor]);
  }
  return out;
}

const R_MI = 3958.7613;
export function haversineMi(a: LngLat, b: LngLat): number {
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad;
  const dLon = (b[0] - a[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R_MI * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function cumulative(path: LngLat[]): number[] {
  const out = [0];
  for (let i = 1; i < path.length; i++) out.push(out[i - 1] + haversineMi(path[i - 1], path[i]));
  return out;
}

/** Slice a path between two mileage marks (marks are in the same units as `cum`). */
export function slicePath(path: LngLat[], cum: number[], from: number, to: number): LngLat[] {
  const at = (m: number): { p: LngLat; i: number } => {
    if (m <= 0) return { p: path[0], i: 0 };
    const total = cum[cum.length - 1];
    if (m >= total) return { p: path[path.length - 1], i: path.length - 1 };
    let lo = 0;
    let hi = cum.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (cum[mid] <= m) lo = mid;
      else hi = mid;
    }
    const seg = cum[hi] - cum[lo];
    const t = seg === 0 ? 0 : (m - cum[lo]) / seg;
    return { p: [path[lo][0] + (path[hi][0] - path[lo][0]) * t, path[lo][1] + (path[hi][1] - path[lo][1]) * t], i: lo };
  };
  const a = at(from);
  const b = at(to);
  const mid = path.slice(a.i + 1, b.i + 1);
  return [a.p, ...mid, b.p];
}
