import { useEffect, useState } from "react";
import { Sparkles, Play, Loader2, ArrowRight, Save, Trash2 } from "lucide-react";
import { api } from "../api";
import type { Strat } from "./QuantPilotApp";
import StrategyEditor from "./StrategyEditor";
import { describeCond, formToSpec, parseUniverse, specToForm } from "./strategyForm";

const STATUS_MAP: Record<string, string> = { draft: "草稿", validated: "已验证", active: "运行中", archived: "已归档" };
const STATUS_CLS: Record<string, string> = { draft: "gray", validated: "blue", active: "green", archived: "gray" };

function Step({ n, title, sub }: { n: number; title: string; sub: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 14 }}>
      <span style={{
        width: 26, height: 26, borderRadius: "50%", background: "var(--primary)", color: "#fff",
        fontSize: 14, fontWeight: 700, display: "grid", placeItems: "center", flex: "none",
      }}>{n}</span>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
        <div className="notice" style={{ margin: 0 }}>{sub}</div>
      </div>
    </div>
  );
}

export default function StrategyLab({ strat }: { strat: Strat }) {
  const { form, setForm, cash, setCash, spec, result, loading, error, run } = strat;
  const [nl, setNl] = useState(
    "帮我设计一个A股成长股策略：股价站上20日均线、20日均线在60日均线上方、成交量放大1.3倍时买入；跌破20日均线卖出；单股最大仓位30%，止损8%。"
  );
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<"ai" | "rule" | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [presets, setPresets] = useState<any[]>([]);
  const [saveName, setSaveName] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);

  const loadStrategies = () => api.strategies().then((r) => setStrategies(r.strategies)).catch(() => {});
  useEffect(() => {
    loadStrategies();
    api.presets().then((r) => setPresets(r.presets)).catch(() => {});
  }, []);

  const loadPreset = (p: any) => {
    setForm(specToForm(p.spec));
    setSaveName("");
    setEditingId(null);
  };

  const editStrategy = async (s: any) => {
    try {
      const d = await api.strategyDetail(s.id);
      setForm(specToForm(d.strategy.config));
      setSaveName(d.strategy.name);
      setEditingId(s.id);
    } catch (e: any) { setErr(`载入失败：${e.message}`); }
  };

  const saveStrategy = async () => {
    setBusy(true); setErr(null);
    try {
      if (editingId != null) {
        await api.updateStrategy(editingId, formToSpec(form), "编辑更新");
      } else {
        await api.strategySave(formToSpec(form), { name: saveName.trim() || form.name, source: "manual" });
      }
      setSaveName("");
      setEditingId(null);
      loadStrategies();
    } catch (e: any) {
      setErr(`保存失败：${e.message}`);
    } finally { setBusy(false); }
  };

  const removeStrategy = async (id: number) => {
    try { await api.deleteStrategy(id); setSelectedIds((x) => x.filter((i) => i !== id)); loadStrategies(); } catch { /* ignore */ }
  };

  const removeSelected = async () => {
    if (!selectedIds.length) return;
    try { await api.deleteStrategies(selectedIds); setSelectedIds([]); loadStrategies(); } catch { /* ignore */ }
  };

  const dedupe = async () => {
    try { await api.dedupeStrategies(); loadStrategies(); } catch { /* ignore */ }
  };

  const syms = parseUniverse(form.universe);
  useEffect(() => {
    if (!syms.length) { setNames({}); return; }
    let alive = true;
    api.stockNames(syms.join(",")).then((r) => { if (alive) setNames(r.names); }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.universe]);

  const parse = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.strategyParse(nl);
      setForm(specToForm(r.spec));
      setWarnings(r.warnings);
      setSource(r.source);
    } catch (e: any) {
      setErr(`AI 解析失败：${e.message}`);
    } finally { setBusy(false); }
  };

  const runBacktest = async () => {
    setBusy(true);
    await run();
    setBusy(false);
    loadStrategies();
  };

  const m = result?.metrics || {};
  const pct = (v: any, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
  const f = (spec.filters || []).map(describeCond).join(" 且 ");
  const e = (spec.entry || []).map(describeCond).join(" 且 ");
  const x = (spec.exit || []).map(describeCond).join(" 或 ");

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {/* 页面说明 */}
      <div className="panel" style={{ marginBottom: 16, background: "var(--primary-weak)", borderColor: "#dfe7fb" }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>这个页面做什么？</div>
        <div className="notice" style={{ margin: 0, color: "var(--text-2)" }}>
          把一句话的"想法"变成一套<strong>可回测的规则</strong>，再看它在历史上赚不赚钱、风险多大。
          规则一旦确定，全站（总览 / 回测中心 / 模拟交易 / 个股分析）都用同一套。
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <span className="pill gray">① 描述想法</span><ArrowRight size={13} style={{ alignSelf: "center", color: "var(--text-3)" }} />
          <span className="pill gray">② 确认规则与风控</span><ArrowRight size={13} style={{ alignSelf: "center", color: "var(--text-3)" }} />
          <span className="pill gray">③ 设本金并运行</span><ArrowRight size={13} style={{ alignSelf: "center", color: "var(--text-3)" }} />
          <span className="pill gray">④ 看结果 / 深入</span>
        </div>
      </div>

      {/* Step 1 */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <Step n={1} title="描述你的想法（可选）" sub="用大白话写；AI 会翻译成下面第 2 步的规则。也可以跳过，直接手填规则。" />
        <textarea value={nl} onChange={(ev) => setNl(ev.target.value)} />
        <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn primary" onClick={parse} disabled={busy}>
            {busy ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />} AI 解析成规则
          </button>
          {source && <span className="pill gray">解析来源：{source === "ai" ? "DeepSeek" : "关键词兜底"}</span>}
          <span className="notice" style={{ margin: 0 }}>解析后的规则出现在第 2 步，可再手动改。</span>
        </div>
        {err && <div className="error" style={{ marginTop: 12 }}>{err}</div>}
        {warnings.length > 0 && (
          <div className="ai-box" style={{ marginTop: 12, borderColor: "#ffe2ad", background: "#fffaf0" }}>
            <div className="who" style={{ color: "#b26a00" }}>解析提示</div>
            {warnings.map((w, i) => <p key={i}>{w}</p>)}
          </div>
        )}
      </div>

      {/* Step 2 */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <Step n={2} title="确认规则与风控" sub="每条规则 = 字段 + 算子 + 值。分组含义：过滤=能不能碰，买入=全部满足才买，卖出=任一满足就卖。" />
        <div className="field">
          <label>预设策略（点一下载入，彼此规则不同）</label>
          <div className="reasons">
            {presets.map((p) => (
              <button key={p.key} className="btn ghost sm" onClick={() => loadPreset(p)} title={p.description}>
                {p.name}
              </button>
            ))}
            {presets.length === 0 && <span className="notice">暂无预设。</span>}
          </div>
        </div>
        <StrategyEditor form={form} onChange={setForm} hideUniverse />

        <div className="ai-box" style={{ marginTop: 4 }}>
          <div className="who">这套策略在说人话</div>
          <p>
            在 <b>{syms.map((s) => names[s] || s).join("、") || "（未设标的）"}</b> 这些标的上：
            {f && <>只有满足 <b>{f}</b> 时才允许持有；</>}
            当 <b>{e || "（未设买入条件）"}</b> 时，次日开盘<b>买入</b>；
            当 <b>{x || "（未设卖出条件）"}</b> 时，次日开盘<b>卖出</b>。
          </p>
          <p>
            风控：单股最多 <b>{form.weight}%</b>，单笔止损 <b>{form.stopLoss}%</b>，
            账户回撤达 <b>{form.drawdownStop}%</b> 熔断并冷却 <b>{form.drawdownCooldown}</b> 个交易日。
          </p>
        </div>
      </div>

      {/* Step 3 */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <Step n={3} title="设置本金并运行回测" sub="本金决定能买得起多少手；回测会模拟真实成交（T+1、整手、费用）。" />
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 220px" }}>
            <label>初始本金（元）</label>
            <input type="number" value={cash} onChange={(ev) => setCash(Number(ev.target.value) || 0)} />
          </div>
          <button className="btn primary" onClick={runBacktest} disabled={busy}>
            {busy ? <Loader2 size={14} className="spin" /> : <Play size={14} />} 运行回测
          </button>
          <span className="notice" style={{ margin: 0 }}>
            跑完可去「回测中心」看逐笔交易，或在「股票雷达」筛选后对单只做「个股分析」。
          </span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
          <div className="field" style={{ marginBottom: 0, flex: "1 1 260px", maxWidth: 320 }}>
            <label>保存到策略库（命名后可复用 / 选择）</label>
            <input value={saveName} onChange={(ev) => setSaveName(ev.target.value)} placeholder={form.name} />
          </div>
          <button className="btn ghost" onClick={saveStrategy} disabled={busy}>
            <Save size={14} /> {editingId != null ? `保存为新版本 (#${editingId})` : "保存为策略"}
          </button>
          {editingId != null && (
            <button className="btn ghost sm" onClick={() => { setEditingId(null); setSaveName(""); }}>取消编辑</button>
          )}
          <span className="notice" style={{ margin: 0 }}>运行回测不会自动保存；只有点这里才会进「策略库」。</span>
        </div>
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}

        {result && (
          <div style={{ marginTop: 16 }}>
            <div className="section-title" style={{ marginBottom: 10 }}>回测结果 {result.run_id ? `（已落库 run#${result.run_id}）` : ""}</div>
            <div className="stat-row">
              <div className="stat"><span className="k">年化收益</span><span className={`v ${(m.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(m.annual_return)}</span><span className="d">累计 {pct(m.total_return)}</span></div>
              <div className="stat"><span className="k">最大回撤</span><span className="v down">{pct(m.max_drawdown)}</span><span className="d">最难受时亏这么多</span></div>
              <div className="stat"><span className="k">夏普比率</span><span className="v">{m.sharpe == null ? "—" : Number(m.sharpe).toFixed(2)}</span><span className="d">每份波动换多少收益</span></div>
              <div className="stat"><span className="k">成交笔数</span><span className="v">{result.trades?.length ?? 0}</span><span className="d">胜率 {pct(m.win_rate, 0)}</span></div>
            </div>
            {(result.trades?.length ?? 0) === 0 && (result.skips?.length ?? 0) > 0 && (
              <div className="ai-box" style={{ marginTop: 12, borderColor: "#ffe2ad", background: "#fffaf0" }}>
                <div className="who" style={{ color: "#b26a00" }}>资金约束生效</div>
                <p>{result.skips[0]?.reason}（共 {result.skips.length} 次被跳过）。系统不会为凑交易强行买入——这是对的。</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 我的策略 */}
      <div className="panel">
        <div className="panel-head">
          <span className="t">策略库（已保存）</span>
          <span className="s">{strategies.length} 个{selectedIds.length ? ` · 已选 ${selectedIds.length}` : ""}</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn ghost sm" onClick={dedupe} title="同名只保留最新一条">清理重复</button>
            <button className="btn ghost sm" onClick={removeSelected} disabled={!selectedIds.length}>
              <Trash2 size={13} /> 删除选中
            </button>
          </div>
        </div>
        <table className="qp-table">
          <thead>
            <tr>
              <th style={{ width: 34 }}>
                <input
                  type="checkbox"
                  checked={strategies.length > 0 && selectedIds.length === strategies.length}
                  onChange={(e) => setSelectedIds(e.target.checked ? strategies.map((s) => s.id) : [])}
                />
              </th>
              <th style={{ textAlign: "left" }}>策略</th><th>版本</th><th>状态</th><th>更新</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <tr key={s.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(s.id)}
                    onChange={(e) => setSelectedIds((x) => e.target.checked ? [...x, s.id] : x.filter((i) => i !== s.id))}
                  />
                </td>
                <td style={{ textAlign: "left" }}>
                  <div className="strong">
                    {s.name}
                    {s.source === "ai" && <span className="pill blue" style={{ marginLeft: 6 }}>AI</span>}
                    {s.source === "discovery" && <span className="pill amber" style={{ marginLeft: 6 }}>逆向</span>}
                    {s.source === "preset" && <span className="pill gray" style={{ marginLeft: 6 }}>预设</span>}
                  </div>
                  <div className="sub" style={{ whiteSpace: "normal", maxWidth: 420, lineHeight: 1.5 }}>{s.description || "—"}</div>
                </td>
                <td className="mono">v{s.current_version}</td>
                <td><span className={`pill ${STATUS_CLS[s.status] ?? "gray"}`}>{STATUS_MAP[s.status] ?? s.status}</span></td>
                <td className="mono sub">{String(s.updated_at).slice(0, 16).replace("T", " ")}</td>
                <td>
                  <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn ghost sm" onClick={() => editStrategy(s)}>编辑</button>
                    <button className="btn ghost sm" onClick={() => removeStrategy(s.id)} title="删除"><Trash2 size={13} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {strategies.length === 0 && <div className="empty">策略库为空。可在上面载入预设，或点「保存为策略」。</div>}
      </div>
    </div>
  );
}
