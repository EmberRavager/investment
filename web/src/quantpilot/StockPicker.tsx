import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { api } from "../api";

function useStockSearch(q: string) {
  const [hits, setHits] = useState<{ symbol: string; name: string }[]>([]);
  useEffect(() => {
    if (!q.trim()) { setHits([]); return; }
    let alive = true;
    const t = setTimeout(() => {
      api.stockSearch(q).then((r) => { if (alive) setHits(r.results); }).catch(() => {});
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [q]);
  return hits;
}

/** 单选股票搜索框（代码或名称都能搜）。 */
export default function StockPicker({
  onPick, placeholder = "搜索股票：代码或名称，如 600519 / 贵州茅台",
}: { onPick: (s: { symbol: string; name: string }) => void; placeholder?: string }) {
  const [q, setQ] = useState("");
  const hits = useStockSearch(q);

  return (
    <div className="search-wrap" style={{ position: "relative", maxWidth: 440 }}>
      <Search size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--text-3)" }} />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        style={{ paddingLeft: 34 }}
      />
      {hits.length > 0 && (
        <div className="search-results">
          {hits.map((h) => (
            <div className="row" key={h.symbol} onClick={() => { onPick(h); setQ(""); }}>
              <span className="nm">{h.name}</span>
              <span className="cd">{h.symbol}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 多选股票池：搜索添加 + 名称标签 + 删除。 */
export function StockPoolPicker({
  symbols, onChange,
}: { symbols: string[]; onChange: (s: string[]) => void }) {
  const [names, setNames] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!symbols.length) { setNames({}); return; }
    let alive = true;
    api.stockNames(symbols.join(",")).then((r) => { if (alive) setNames(r.names); }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(",")]);

  const add = (s: { symbol: string; name: string }) => {
    if (!symbols.includes(s.symbol)) onChange([...symbols, s.symbol]);
  };
  const remove = (sym: string) => onChange(symbols.filter((x) => x !== sym));

  return (
    <div>
      <StockPicker onPick={add} placeholder="搜索并添加股票（代码或名称）" />
      <div className="reasons" style={{ marginTop: 10 }}>
        {symbols.map((s) => (
          <span className="reason" key={s} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {names[s] && names[s] !== s ? names[s] : "…"}
            <span className="mono sub">{s}</span>
            <button className="link" onClick={() => remove(s)} style={{ padding: 0 }} aria-label="移除">
              <X size={12} />
            </button>
          </span>
        ))}
        {symbols.length === 0 && <span className="notice">还没有标的；雷达里也可以直接用「全市场」。</span>}
      </div>
    </div>
  );
}
