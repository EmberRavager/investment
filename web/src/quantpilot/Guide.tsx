import { BookOpen, Compass, Radar, FlaskConical, BarChart3, LineChart, Wallet, Boxes } from "lucide-react";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
      <span style={{
        width: 24, height: 24, borderRadius: "50%", background: "var(--primary)", color: "#fff",
        fontSize: 13, fontWeight: 700, display: "grid", placeItems: "center", flex: "none", marginTop: 2,
      }}>{n}</span>
      <div>
        <div style={{ fontSize: 14.5, fontWeight: 700, marginBottom: 3 }}>{title}</div>
        <div style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.8 }}>{children}</div>
      </div>
    </div>
  );
}

const PAGES: [any, string, string][] = [
  [Radar, "股票雷达", "用当前策略对全市场/ETF/指数成分做筛选，给出候选与触发原因；可对单只做「个股分析」。"],
  [BarChart3, "个股分析", "选任意股票，看当前策略在这只票上的历史表现（年化/回撤/年度月度收益/逐笔）。"],
  [Compass, "逆向发现", "反着来：选一只股票，搜索规则空间，找出在该股上样本外表现稳健的策略。"],
  [Boxes, "多因子选股", "横截面多因子（Alpha158 + 模型打分）选 top-k 组合，含 IC/分层/超额/组合优化。"],
  [FlaskConical, "策略实验室", "用自然语言或手动编辑规则、设风控与本金，运行回测；策略库可增删改查。"],
  [LineChart, "回测中心", "当前策略的完整回测：指标、样本内/外、逐笔成交、成本、AI 反思。"],
  [Wallet, "模拟交易", "按策略生成模拟账户（持仓/订单），并做「模拟盘跟踪」用真实行情事后验证。"],
];

export default function Guide() {
  return (
    <div style={{ maxWidth: 980, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 16, background: "var(--primary-weak)", borderColor: "#dfe7fb" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 16, fontWeight: 700, marginBottom: 8 }}>
          <BookOpen size={18} /> 使用说明
        </div>
        <div className="notice" style={{ margin: 0, color: "var(--text-2)" }}>
          QuantPilot 是**研究/验证平台**：把想法变成可回测的规则，严格验证后再决定是否采用。
          <b> 所有结果不构成投资建议，未通过验收前勿用于实盘。</b>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head"><span className="t">快速上手（3 步）</span></div>
        <Step n={1} title="在「策略实验室」准备一套策略">
          用大白话描述（点「AI 解析」）或直接手动设规则；设定单股仓位、止损、熔断。预设策略可一键载入。
        </Step>
        <Step n={2} title="去「股票雷达」或「多因子选股」找标的">
          雷达用**规则**筛全市场（受风控/资金约束，B－买不起会明说）；多因子用**模型打分**选一篮子。
        </Step>
        <Step n={3} title="在「回测中心 / 个股分析 / 模拟交易」验证">
          看样本外表现、超额、成本；把选股「记录到模拟盘」，持有期结束后在「模拟交易」页**结算**，
          用真实行情检验——“能不能用”由这一步说话。
        </Step>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head"><span className="t">各页面作用</span></div>
        <table className="qp-table">
          <tbody>
            {PAGES.map(([Icon, name, desc]) => (
              <tr key={name}>
                <td style={{ textAlign: "left", whiteSpace: "nowrap", width: 140 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 700 }}>
                    <Icon size={15} /> {name}
                  </span>
                </td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="qp-grid side" style={{ marginBottom: 16 }}>
        <div className="panel">
          <div className="panel-head"><span className="t">推荐工作流</span></div>
          <div className="notice" style={{ margin: 0, lineHeight: 2 }}>
            ① 策略实验室：定义/载入策略 → ② 股票雷达：看全市场触发 →
            ③ 个股分析：确认单票历史 → ④ 回测中心：看样本内/外与超额 →
            ⑤ 模拟交易：记录并结算跟踪 → ⑥ 通过验收门槛才考虑小资金实盘。
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><span className="t">结果怎么看</span></div>
          <div className="notice" style={{ margin: 0, lineHeight: 2 }}>
            • <b>IC / ICIR</b>（多因子）：打分与未来收益的相关性，越接近 0 越没用。<br />
            • <b>年化 / 最大回撤 / 夏普</b>：收益与风险。<br />
            • <b>样本外</b>：策略没"见过"的时间段，比全样本可信。<br />
            • <b>超额 vs 指数</b>：扣除成本后是否跑赢沪深300。<br />
            • <b>验收徽标</b>：红＝未通过·勿实盘，绿＝通过初步验收（仍需模拟盘）。
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><span className="t">常见问题</span></div>
        <div className="notice" style={{ margin: 0, lineHeight: 2 }}>
          • <b>为什么选出的股票年化是负的？</b> 雷达选的是"今天满足规则"，不代表这套规则历史有效。<br />
          • <b>为什么显示"再买不起/超出仓位限制"？</b> 本金与单股上限决定的真实约束，系统不会为凑交易强行买入。<br />
          • <b>为什么刷新后停在当前页？</b> 已用 hash 路由，地址栏 `#/页面` 可分享/收藏。<br />
          • <b>AI 解析/反思没反应？</b> 需配置 `DEEPSEEK_API_KEY`；无 key 时策略解析走关键词兜底。<br />
          • <b>数据是真的吗？</b> 行情来自 akshare/baostock 真实数据；账户/持仓是据此计算的模拟结果。
        </div>
      </div>
    </div>
  );
}
