import { Search, SlidersHorizontal, LineChart, AlertTriangle } from "lucide-react";

export default function Onboarding({ onClose }: { onClose: () => void }) {
  return (
    <div className="onboard">
      <h2>你好！这个工具帮你判断：一只股票现在该不该买</h2>
      <p>
        它会把一只股票过去好几年的价格翻出来，模拟一套「买卖办法」，看看如果一直照着做，
        是赚还是亏、亏最多亏多少。
      </p>

      <div className="how">
        <div className="item">
          <Search className="ic" size={20} />
          <b>1. 选一只股票</b>
          <span>直接打字，比如「茅台」，不用记代码</span>
        </div>
        <div className="item">
          <SlidersHorizontal className="ic" size={20} />
          <b>2. 选一种风格</b>
          <span>想稳一点，还是想搏一搏</span>
        </div>
        <div className="item">
          <LineChart className="ic" size={20} />
          <b>3. 看结论</b>
          <span>用大白话告诉你结果，不用懂术语</span>
        </div>
      </div>

      <div className="warnbox">
        <AlertTriangle size={18} style={{ flex: "none", marginTop: 2, color: "var(--warn)" }} />
        <span>
          <b>重要提醒：</b>结果只是「用历史数据试一试」，<b>不是投资建议</b>。市场没有谁能保证赚钱，请务必谨慎。
        </span>
      </div>

      <div style={{ marginTop: 14 }}>
        <button onClick={onClose}>我知道了，开始用 →</button>
      </div>
    </div>
  );
}
