import { useCallback, useEffect, useRef, useState } from "react";
import { StockSDK } from "stock-sdk";

// 主要指数（stock-sdk 直接取实时行情，浏览器端直连）
const INDICES: { code: string; name: string }[] = [
  { code: "sh000001", name: "上证指数" },
  { code: "sz399001", name: "深证成指" },
  { code: "sz399006", name: "创业板指" },
  { code: "sh000300", name: "沪深300" },
  { code: "sh000688", name: "科创50" },
  { code: "sh000905", name: "中证500" },
];

interface Row {
  code: string;
  name: string;
  price: number;
  changePercent: number;
  amount: number;
}

export default function MarketBoard() {
  const sdkRef = useRef<StockSDK | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [updated, setUpdated] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (!sdkRef.current) sdkRef.current = new StockSDK();
      const codes = INDICES.map((i) => i.code);
      const quotes: any[] = await sdkRef.current.quotes.cn(codes);
      const byCode = new Map(quotes.map((q) => [q.code, q]));
      const mapped: Row[] = INDICES.map((i) => {
        const q = byCode.get(i.code.replace(/^(sh|sz)/, "")) ?? byCode.get(i.code);
        return {
          code: i.code,
          name: q?.name && q.name !== "" ? q.name : i.name,
          price: Number(q?.price ?? NaN),
          changePercent: Number(q?.changePercent ?? NaN),
          amount: Number(q?.amount ?? NaN),
        };
      });
      setRows(mapped);
      setUpdated(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    } catch (e: any) {
      setError(
        `实时行情获取失败：${e?.message ?? e}。stock-sdk 走浏览器直连，若被 CORS 拦截需经代理。`
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const cls = (v: number) => (Number.isNaN(v) ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const fmtPct = (v: number) =>
    Number.isNaN(v) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const fmtPrice = (v: number) => (Number.isNaN(v) ? "—" : v.toFixed(2));

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="head">
        <span className="t">大盘实时行情</span>
        <span className="s">
          {updated && `更新 ${updated}`} · 30s 自动刷新
          <button
            onClick={load}
            disabled={loading}
            style={{ marginLeft: 12, padding: "3px 10px" }}
          >
            {loading ? "…" : "刷新"}
          </button>
        </span>
      </div>
      {error ? (
        <div className="hint">{error}</div>
      ) : rows.length === 0 ? (
        <div className="hint">加载中…</div>
      ) : (
        <div className="index-grid">
          {rows.map((r) => (
            <div className="index-cell" key={r.code}>
              <div className="nm">{r.name}</div>
              <div className={`px ${cls(r.changePercent)}`}>{fmtPrice(r.price)}</div>
              <div className={`cp ${cls(r.changePercent)}`}>{fmtPct(r.changePercent)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
