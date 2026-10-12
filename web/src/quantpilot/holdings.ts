// 用户真实持仓（本地保存）。
export interface Holding {
  id: string;
  symbol: string;
  name: string;
  qty: number;      // 股数
  cost: number;     // 买入成本价（每股）
}

const KEY = "qp_holdings_v1";

export function uid(): string {
  return Math.random().toString(36).slice(2, 9);
}

export function loadHoldings(): Holding[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

export function saveHoldings(h: Holding[]): void {
  localStorage.setItem(KEY, JSON.stringify(h));
}
