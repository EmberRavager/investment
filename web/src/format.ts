export const pct = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
};

export const num = (v: number | null | undefined, digits = 3): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
};

/** A 股习惯：红涨绿跌。返回颜色类名。 */
export const upDown = (v: number | null | undefined): string => {
  if (v === null || v === undefined || Number.isNaN(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
};

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
