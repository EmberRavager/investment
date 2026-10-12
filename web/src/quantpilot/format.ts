// 行情日期展示：区分"今天"和"数据源最新交易日"。
export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** 数据源最新交易日说明；若最新日 < 今天，提示今日行情可能尚未更新/非交易日。 */
export function asOfText(asOf?: string): string {
  if (!asOf) return "";
  const t = todayISO();
  if (asOf === t) return `数据源最新交易日 ${asOf}`;
  return `数据源最新交易日 ${asOf}（今日 ${t} 行情尚未更新或当日非交易日）`;
}
