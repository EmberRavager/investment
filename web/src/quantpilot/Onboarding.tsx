import { Radar, FlaskConical, Wallet, BookOpen, X, ArrowRight } from "lucide-react";

export default function Onboarding({ onClose, onGo }: { onClose: () => void; onGo: (k: string) => void }) {
  return (
    <div className="qp-drawer-mask" onClick={onClose}>
      <div className="qp-onboard" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head" style={{ marginBottom: 6 }}>
          <span className="t" style={{ fontSize: 17 }}>欢迎使用 QuantPilot</span>
          <button className="link" onClick={onClose} aria-label="关闭"><X size={16} /></button>
        </div>
        <div className="notice" style={{ margin: "0 0 16px" }}>
          这是**量化研究/验证平台**。第一次用，照下面 3 步走即可：
        </div>

        <div className="onb-step">
          <span className="n">1</span>
          <div>
            <b><FlaskConical size={14} /> 在「策略实验室」准备策略</b>
            <p>用大白话描述再点「AI 解析」，或直接**载入预设策略**（如"趋势跟随"）。设好仓位/止损。</p>
          </div>
        </div>
        <div className="onb-step">
          <span className="n">2</span>
          <div>
            <b><Radar size={14} /> 在「股票雷达」找标的</b>
            <p>选「全市场 / ETF / 指数成分」，点「筛选」。列表里绿字＝满足买入，红字＝被风控拒绝（原因会写明）。</p>
          </div>
        </div>
        <div className="onb-step">
          <span className="n">3</span>
          <div>
            <b><Wallet size={14} /> 在「模拟交易」验证</b>
            <p>记录选股 → 到期「结算」，用真实行情看收益/超额/命中率。**通过验收再考虑实盘**。</p>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
          <button className="btn primary" onClick={() => onGo("lab")}>
            <FlaskConical size={14} /> 从策略实验室开始 <ArrowRight size={13} />
          </button>
          <button className="btn ghost" onClick={() => onGo("radar")}><Radar size={14} /> 直接去选股</button>
          <button className="btn ghost" onClick={() => onGo("guide")}><BookOpen size={14} /> 查看使用说明</button>
        </div>

        <div className="notice" style={{ marginTop: 14 }}>
          ⚠️ 研究用途·未验证·勿用于实盘；所有结果不构成投资建议。
        </div>
      </div>
    </div>
  );
}
