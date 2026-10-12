import { StockSDK } from "stock-sdk";

let sdk: StockSDK | null = null;

function prefix(sym: string): string {
  const s = String(sym);
  if (s.startsWith("6") || s.startsWith("9")) return "sh" + s;
  if (s.startsWith("4") || s.startsWith("8")) return "bj" + s;
  return "sz" + s;
}

export interface Quote {
  price: number;
  name: string;
  changePercent: number;
}

/** 用 stock-sdk 取实时行情（浏览器直连，失败返回 {}）。 */
export async function fetchQuotes(symbols: string[]): Promise<Record<string, Quote>> {
  const syms = symbols.filter(Boolean);
  if (!syms.length) return {};
  try {
    if (!sdk) sdk = new StockSDK();
    const codes = syms.map(prefix);
    const quotes: any[] = await sdk.quotes.cn(codes);
    const byCode = new Map(quotes.map((q) => [String(q.code), q]));
    const out: Record<string, Quote> = {};
    syms.forEach((s, i) => {
      const bare = codes[i].replace(/^(sh|sz|bj)/, "");
      const q = byCode.get(bare) ?? byCode.get(codes[i]);
      if (q && Number.isFinite(Number(q.price))) {
        out[s] = { price: Number(q.price), name: q.name || s, changePercent: Number(q.changePercent) || 0 };
      }
    });
    return out;
  } catch {
    return {};
  }
}
