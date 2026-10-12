import { useEffect, useState } from "react";
import { api } from "../api";
import type { Strat } from "./QuantPilotApp";
import { specToForm } from "./strategyForm";

/** 模块内使用的策略选择器：从策略库载入一条到"当前策略"（全站共用）。 */
export default function StrategySelector({
  strat, label = "使用策略",
}: { strat: Strat; label?: string }) {
  const [list, setList] = useState<any[]>([]);
  const [cur, setCur] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = () => api.strategies().then((r) => setList(r.strategies)).catch(() => {});
  useEffect(() => { reload(); }, []);

  const load = async (id: string) => {
    setCur(id);
    if (!id) return;
    setBusy(true);
    try {
      const d = await api.strategyDetail(Number(id));
      strat.setForm(specToForm(d.strategy.config));
    } catch { /* ignore */ } finally { setBusy(false); }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
      <span className="notice" style={{ margin: 0 }}>{label}</span>
      <select
        value={cur}
        onChange={(e) => load(e.target.value)}
        onClick={reload}
        disabled={busy}
        style={{ width: 210, padding: "5px 9px", fontSize: 12.5 }}
      >
        <option value="">当前：{strat.spec.name}</option>
        {list.map((s) => (
          <option key={s.id} value={s.id}>{s.name} · v{s.current_version}</option>
        ))}
      </select>
    </span>
  );
}
