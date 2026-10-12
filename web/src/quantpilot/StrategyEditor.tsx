import { Plus, Trash2 } from "lucide-react";
import {
  FIELD_GROUPS, OPS, parseUniverse, type Condition, type StrategyForm,
} from "./strategyForm";
import { StockPoolPicker } from "./StockPicker";

function ConditionRow({
  c, onChange, onRemove,
}: { c: Condition; onChange: (c: Condition) => void; onRemove: () => void }) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <select value={c.field} onChange={(e) => onChange({ ...c, field: e.target.value })} style={{ flex: "1 1 130px" }}>
        {FIELD_GROUPS.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.fields.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </optgroup>
        ))}
      </select>
      <select value={c.op} onChange={(e) => onChange({ ...c, op: e.target.value })} style={{ flex: "0 0 84px" }}>
        {OPS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
      </select>
      <input
        value={String(c.value)}
        onChange={(e) => onChange({ ...c, value: e.target.value })}
        placeholder="数字或字段名，如 1.3 / ma60"
        style={{ flex: "1 1 120px" }}
      />
      <button className="link" onClick={onRemove} aria-label="删除"><Trash2 size={14} /></button>
    </div>
  );
}

function Group({
  title, hint, kind, items, set,
}: {
  title: string; hint: string; kind: string; items: Condition[]; set: (c: Condition[]) => void;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
        <span className={`tag ${kind}`}>{title}</span>
        <span className="notice" style={{ margin: 0 }}>{hint}</span>
        <button className="link" style={{ marginLeft: "auto" }} onClick={() => set([...items, { field: "close", op: ">", value: "" }])}>
          <Plus size={13} style={{ verticalAlign: -2 }} /> 添加
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((c, i) => (
          <ConditionRow
            key={i}
            c={c}
            onChange={(nc) => set(items.map((x, j) => (j === i ? nc : x)))}
            onRemove={() => set(items.filter((_, j) => j !== i))}
          />
        ))}
        {items.length === 0 && <div className="notice">暂无条件。</div>}
      </div>
    </div>
  );
}

export default function StrategyEditor({
  form, onChange, hideUniverse = false, hideName = false,
}: {
  form: StrategyForm;
  onChange: (f: StrategyForm) => void;
  hideUniverse?: boolean;
  hideName?: boolean;
}) {
  const set = (patch: Partial<StrategyForm>) => onChange({ ...form, ...patch });
  const syms = parseUniverse(form.universe);

  return (
    <>
      {!hideName && (
        <div className="field">
          <label>策略名称</label>
          <input value={form.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
      )}
      {!hideUniverse && (
        <div className="field">
          <label>股票池（搜索添加；雷达里也可直接用全市场）</label>
          <StockPoolPicker symbols={syms} onChange={(list) => set({ universe: list.join(",") })} />
        </div>
      )}

      <Group
        title="过滤" kind="filter" hint="不满足则不允许持仓"
        items={form.filters} set={(filters) => set({ filters })}
      />
      <Group
        title="买入" kind="entry" hint="全部满足 → 次日开盘买入"
        items={form.entry} set={(entry) => set({ entry })}
      />
      <Group
        title="卖出" kind="exit" hint="任一满足 → 次日开盘卖出"
        items={form.exit} set={(exit) => set({ exit })}
      />

      <div className="qp-grid c2" style={{ marginTop: 4 }}>
        <div className="field">
          <label>单股最大仓位 (%)</label>
          <input type="number" value={form.weight} onChange={(e) => set({ weight: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>止损 (%)</label>
          <input type="number" value={form.stopLoss} onChange={(e) => set({ stopLoss: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>回撤熔断 (%)</label>
          <input type="number" value={form.drawdownStop} onChange={(e) => set({ drawdownStop: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>熔断后冷却 (交易日)</label>
          <input type="number" value={form.drawdownCooldown} onChange={(e) => set({ drawdownCooldown: Number(e.target.value) })} />
        </div>
      </div>
    </>
  );
}
