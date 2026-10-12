// 侧边导航（结构配置）。
export interface NavKey {
  key: string;
  label: string;
  hint: string;
}

export const NAV: NavKey[] = [
  { key: "overview", label: "总览", hint: "账户、净值与今日信号" },
  { key: "radar", label: "股票雷达", hint: "全市场选股与触发规则" },
  { key: "stock", label: "个股分析", hint: "单只股票的策略历史表现" },
  { key: "discovery", label: "逆向发现", hint: "从一只股票反推策略" },
  { key: "xsec", label: "多因子选股", hint: "横截面因子 + 模型打分" },
  { key: "lab", label: "策略实验室", hint: "描述 / 调整策略并回测" },
  { key: "backtest", label: "回测中心", hint: "历史验证与交易明细" },
  { key: "paper", label: "模拟交易", hint: "持仓、订单与资金" },
];
