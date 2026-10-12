// 统一的"是否达到可用门槛"判定（保守：默认红色，除非通过硬门槛）。
export interface Verdict {
  usable: boolean;
  label: string;
  reasons: string[];
}

export function verdictOf(metrics: any, splits?: any, excess?: number | null): Verdict {
  const m = metrics || {};
  const oos = splits?.out_sample || {};
  const reasons: string[] = [];

  const annual = m.annual_return;
  const sharpe = m.sharpe;
  const dd = m.max_drawdown;
  const oosSharpe = oos.sharpe;
  const oosAnnual = oos.annual_return;
  const trades = m.num_trades ?? m.round_trips;

  if (annual != null && annual <= 0) reasons.push("全样本年化为负");
  if (sharpe != null && sharpe < 0.5) reasons.push(`夏普 ${Number(sharpe).toFixed(2)} < 0.5`);
  if (oosSharpe != null && oosSharpe < 0.3) reasons.push(`样本外夏普 ${Number(oosSharpe).toFixed(2)} < 0.3`);
  if (oosAnnual != null && oosAnnual <= 0) reasons.push("样本外年化为负");
  if (excess != null && excess <= 0) reasons.push("未跑赢基准（无超额）");
  if (trades != null && trades < 20) reasons.push(`成交/回合仅 ${trades}，样本不足`);
  if (dd != null && dd < -0.4) reasons.push(`最大回撤 ${(dd * 100).toFixed(0)}% 偏大`);

  const usable = reasons.length === 0;
  return {
    usable,
    label: usable ? "通过初步验收（仍需模拟盘验证）" : "未通过验收 · 勿实盘",
    reasons,
  };
}
