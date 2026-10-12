import { ShieldAlert } from "lucide-react";

/** 常驻安全提示：研究用途、未验证、勿实盘。 */
export default function ResearchBanner() {
  return (
    <div className="qp-research-banner">
      <ShieldAlert size={15} />
      <span>
        <b>研究用途 · 未经验证 · 勿用于实盘</b>。本项目为量化研究与决策框架，
        历史回测不代表未来，所有数据与信号<b>不构成投资建议</b>；实盘前必须通过验收门槛并完成模拟盘验证。
      </span>
    </div>
  );
}
