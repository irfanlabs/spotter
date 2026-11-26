export interface FormValues {
  originText: string;
  destText: string;
  departure: string; // datetime-local
  load: string; // digits, possibly with commas
}

export type FieldErrors = Partial<Record<"origin" | "destination" | "departure" | "load", string>>;

export const MAX_LOAD = 80_000;

export function parseLoad(raw: string): number {
  return Number(raw.replace(/[, ]/g, ""));
}

export function validate(v: FormValues, hasOrigin: boolean, hasDest: boolean, now = new Date()): FieldErrors {
  const e: FieldErrors = {};
  if (!v.originText.trim() && !hasOrigin) e.origin = "Enter a starting location.";
  if (!v.destText.trim() && !hasDest) e.destination = "Enter a destination.";

  if (!v.departure) e.departure = "Choose a departure date and time.";
  else {
    const t = new Date(v.departure).getTime();
    if (Number.isNaN(t)) e.departure = "That date isn't valid.";
    else if (t < now.getTime() - 2 * 3600_000) e.departure = "Departure can't be in the past.";
    else if (t > now.getTime() + 14 * 86400_000) e.departure = "Forecasts only cover the next 14 days.";
  }

  const load = parseLoad(v.load);
  if (!v.load.trim()) e.load = "Enter the load weight in pounds.";
  else if (!Number.isFinite(load) || !/^-?[\d,\s]+(\.\d+)?$/.test(v.load.trim())) e.load = "Use numbers only, e.g. 38,000.";
  else if (load < 0) e.load = "Weight can't be negative.";
  else if (load > MAX_LOAD) e.load = `Maximum is ${MAX_LOAD.toLocaleString()} lb (US legal limit).`;
  return e;
}
