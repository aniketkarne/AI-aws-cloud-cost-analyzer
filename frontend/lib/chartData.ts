/**
 * Derive plottable (label, value) points from query result rows.
 *
 * The /ask endpoint returns rows keyed by the raw column names of the
 * LLM-generated SQL (e.g. `region`/`total_cost`, not `service`/`cost`),
 * so chart input cannot assume fixed keys. Column selection prefers the
 * caller's expected keys and falls back to the first sensible column.
 * Rows without a finite numeric value are dropped, never charted as NaN.
 */
export interface ChartPoint {
  label: string;
  value: number;
}

type Row = Record<string, unknown>;

function toFiniteNumber(v: unknown): number {
  if (typeof v === 'number') return Number.isFinite(v) ? v : NaN;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : NaN;
  }
  return NaN;
}

function rowKeys(rows: Row[]): string[] {
  const keys: string[] = [];
  for (const row of rows) {
    for (const k of Object.keys(row ?? {})) {
      if (!keys.includes(k)) keys.push(k);
    }
  }
  return keys;
}

/** First column with at least one finite numeric value; preferred key first. */
export function pickValueKey(rows: Row[], preferred?: string): string | null {
  const keys = rowKeys(rows);
  const candidates =
    preferred && keys.includes(preferred)
      ? [preferred, ...keys.filter((k) => k !== preferred)]
      : keys;
  for (const k of candidates) {
    if (rows.some((row) => Number.isFinite(toFiniteNumber(row?.[k])))) return k;
  }
  return null;
}

/** Preferred key if present, else first column of plain string/number values. */
export function pickLabelKey(
  rows: Row[],
  preferred: string | undefined,
  valueKey: string | null
): string | null {
  const keys = rowKeys(rows);
  if (preferred && keys.includes(preferred)) return preferred;
  for (const k of keys) {
    if (k === valueKey) continue;
    const values = rows.map((row) => row?.[k]).filter((v) => v != null);
    if (
      values.length > 0 &&
      values.every((v) => typeof v === 'string' || typeof v === 'number')
    ) {
      return k;
    }
  }
  return null;
}

export function toChartPoints(
  data: unknown,
  preferredLabel?: string,
  preferredValue?: string
): ChartPoint[] {
  if (!Array.isArray(data) || data.length === 0) return [];
  const rows = data.filter((r): r is Row => r != null && typeof r === 'object');
  if (rows.length === 0) return [];

  const valueKey = pickValueKey(rows, preferredValue);
  if (!valueKey) return [];
  const labelKey = pickLabelKey(rows, preferredLabel, valueKey);

  const points: ChartPoint[] = [];
  rows.forEach((row, i) => {
    const value = toFiniteNumber(row[valueKey]);
    if (!Number.isFinite(value)) return;
    const raw = labelKey ? row[labelKey] : null;
    const label =
      raw == null || String(raw).trim() === '' ? `#${i + 1}` : String(raw);
    points.push({ label, value });
  });
  return points;
}
