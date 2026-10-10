import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import type { Health, Summary } from "../types";

export default function ReflectionPanel({
  summary,
  health,
}: {
  summary: Summary;
  health: Health | null;
}) {
  const [mode, setMode] = useState<"single" | "panel">("single");
  const [single, setSingle] = useState("");
  const [panel, setPanel] = useState<Record<string, string>>({});
  const [active, setActive] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const configured = health?.deepseek_configured;

  const run = async (question?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.reflect(summary, question || undefined, mode);
      if (mode === "panel") {
        const p = res.panel ?? {};
        setPanel(p);
        setActive("综合裁决" in p ? "综合裁决" : Object.keys(p)[0] ?? "");
      } else {
        setSingle(res.reflection ?? "");
      }
      setQ("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const hasResult = mode === "panel" ? Object.keys(panel).length > 0 : !!single;

  return (
    <div className="card">
      <div className="head">
        <div className="reflect-head">
          <span className="t">AI 反思 · 严格风控评审</span>
          <span className="s">DeepSeek</span>
        </div>
        <div className="mode-switch">
          <button className={mode === "single" ? "active" : ""} onClick={() => setMode("single")}>
            单次评审
          </button>
          <button className={mode === "panel" ? "active" : ""} onClick={() => setMode("panel")}>
            多 Agent 复盘
          </button>
          <button onClick={() => run()} disabled={loading || !configured}>
            {loading ? "评审中…" : hasResult ? "重新评审" : "运行"}
          </button>
        </div>
      </div>

      {mode === "panel" && (
        <div className="hint">
          风控官 / 量化研究员 / 逆向交易员 / 执行纪律官 四视角独立评审，再由综合裁判汇总裁决。
        </div>
      )}

      {!configured && (
        <div className="hint">
          未配置 <code>DEEPSEEK_API_KEY</code>。启动后端前设置环境变量即可启用：
          <br />
          <code>DEEPSEEK_API_KEY=sk-xxx .venv/bin/uvicorn server.app:app --port 8000</code>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {mode === "single" && single && (
        <div className="reflect-body">
          <ReactMarkdown>{single}</ReactMarkdown>
        </div>
      )}

      {mode === "panel" && Object.keys(panel).length > 0 && (
        <>
          <div className="panel-tabs">
            {Object.keys(panel).map((k) => (
              <button key={k} className={active === k ? "active" : ""} onClick={() => setActive(k)}>
                {k}
              </button>
            ))}
          </div>
          <div className="reflect-body agent-block">
            <div className="who">{active}</div>
            <ReactMarkdown>{panel[active] ?? ""}</ReactMarkdown>
          </div>
        </>
      )}

      <div className="q-input">
        <input
          placeholder="追问模型（可选），例如：这套策略最大的风险是什么？"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && configured && !loading) run(q);
          }}
          disabled={!configured}
        />
        <button onClick={() => run(q)} disabled={loading || !configured || !q.trim()}>
          追问
        </button>
      </div>
    </div>
  );
}
