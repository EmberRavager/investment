// 策略表单 <-> 结构化规格（StrategySpec）。
// 表单就是用户能改的规则集合；spec 是后端确定性规则引擎吃的配置。

export interface Condition {
  field: string;
  op: string;
  value: string | number;
}

export interface StrategyForm {
  name: string;
  universe: string;
  filters: Condition[];
  entry: Condition[];
  exit: Condition[];
  weight: number;
  stopLoss: number;
  drawdownStop: number;
  drawdownCooldown: number;
}

export const FIELD_GROUPS: { label: string; fields: [string, string][] }[] = [
  { label: "价格", fields: [["close", "收盘价"], ["open", "开盘价"], ["high", "最高价"], ["low", "最低价"]] },
  { label: "均线", fields: [["ma5", "5日线"], ["ma10", "10日线"], ["ma20", "20日线"], ["ma60", "60日线"], ["ma120", "120日线"]] },
  { label: "量能", fields: [["volume", "成交量"], ["vol_ratio", "量比"], ["amount", "成交额"]] },
  { label: "动量/强弱", fields: [["ret5", "5日动量"], ["ret20", "20日动量"], ["rsi14", "RSI(14)"], ["pct_chg", "当日涨跌幅"]] },
  { label: "通道", fields: [["high20", "20日最高"], ["low20", "20日最低"]] },
];

export const OPS: [string, string][] = [
  [">", "大于"], ["<", "小于"], [">=", "≥"], ["<=", "≤"], ["==", "等于"],
  ["cross_above", "上穿"], ["cross_below", "下穿"],
];

export const FIELD_LABELS: Record<string, string> = Object.fromEntries(
  FIELD_GROUPS.flatMap((g) => g.fields)
);
export const OP_LABELS: Record<string, string> = Object.fromEntries(OPS);

export const DEFAULT_FORM: StrategyForm = {
  name: "成长趋势跟随",
  universe: "600519,000858,600036,601318,600900,300750,002594,000001",
  filters: [{ field: "ma20", op: ">", value: "ma60" }],
  entry: [{ field: "close", op: ">", value: "ma20" }, { field: "vol_ratio", op: ">", value: 1.3 }],
  exit: [{ field: "close", op: "<", value: "ma20" }],
  weight: 30,
  stopLoss: 8,
  drawdownStop: 15,
  drawdownCooldown: 20,
};

export function parseUniverse(text: string): string[] {
  return text.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
}

function normValue(v: string | number): string | number {
  if (typeof v === "number") return v;
  const s = String(v).trim();
  if (s !== "" && !Number.isNaN(Number(s))) return Number(s);
  return s;
}

function normConditions(cs: Condition[]): any[] {
  return cs
    .filter((c) => c.field && c.op && c.value !== "" && c.value !== undefined)
    .map((c) => ({ field: c.field, op: c.op, value: normValue(c.value) }));
}

export function formToSpec(f: StrategyForm): any {
  return {
    name: f.name || "自定义策略",
    universe: parseUniverse(f.universe),
    filters: normConditions(f.filters),
    entry: normConditions(f.entry),
    exit: normConditions(f.exit),
    weight: f.weight / 100,
    max_position_per_stock: f.weight / 100,
    max_total_exposure: 1.0,
    stop_loss: f.stopLoss / 100,
    drawdown_stop: f.drawdownStop / 100,
    drawdown_cooldown: f.drawdownCooldown,
  };
}

function toCond(c: any): Condition {
  return { field: String(c.field), op: String(c.op), value: c.value };
}

export function specToForm(spec: any): StrategyForm {
  const f: StrategyForm = {
    ...DEFAULT_FORM,
    name: spec?.name || DEFAULT_FORM.name,
    filters: [], entry: [], exit: [],
  };
  if (Array.isArray(spec?.universe) && spec.universe.length) f.universe = spec.universe.join(",");
  f.filters = (spec?.filters || []).map(toCond);
  f.entry = (spec?.entry || []).map(toCond);
  f.exit = (spec?.exit || []).map(toCond);
  if (spec?.max_position_per_stock != null) f.weight = Math.round(spec.max_position_per_stock * 100);
  if (spec?.stop_loss != null) f.stopLoss = Math.round(spec.stop_loss * 100);
  if (spec?.drawdown_stop != null) f.drawdownStop = Math.round(spec.drawdown_stop * 100);
  if (spec?.drawdown_cooldown != null) f.drawdownCooldown = spec.drawdown_cooldown;
  return f;
}

export function describeCond(c: Condition): string {
  const f = FIELD_LABELS[c.field] ?? c.field;
  const v = typeof c.value === "string" && FIELD_LABELS[c.value] ? FIELD_LABELS[c.value] : c.value;
  return `${f} ${OP_LABELS[c.op] ?? c.op} ${v}`;
}
