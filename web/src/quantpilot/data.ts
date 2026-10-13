// 侧边导航（按工作流分组，带步骤编号，帮助新用户建立主线）。
export interface NavKey {
  key: string;
  label: string;
  hint: string;
  group: string;
}

export const NAV: NavKey[] = [
  { key: "guide", label: "使用说明", hint: "先看这个：怎么用", group: "开始" },

  { key: "lab", label: "① 策略实验室", hint: "先定义/载入一套策略", group: "怎么用" },
  { key: "radar", label: "② 股票雷达", hint: "用策略筛全市场/ETF", group: "怎么用" },

  { key: "xsec", label: "多因子选股（进阶）", hint: "横截面模型打分选股", group: "更多选股方式" },
  { key: "discovery", label: "逆向发现", hint: "从一只股票反推策略", group: "更多选股方式" },

  { key: "stock", label: "个股分析", hint: "看某只票的历史表现", group: "看结果" },
  { key: "backtest", label: "回测中心", hint: "策略整体表现与交易明细", group: "看结果" },
  { key: "paper", label: "模拟交易", hint: "模拟账户 + 跟踪验证", group: "看结果" },
  { key: "overview", label: "我的持仓", hint: "你自己添加的持仓与信号", group: "看结果" },
];

//: 主线"下一步"映射（把用户顺着流程带下去）
export const NEXT: Record<string, string> = {
  guide: "lab",
  lab: "radar",
  radar: "stock",
  stock: "backtest",
  backtest: "paper",
  paper: "overview",
  overview: "radar",
  xsec: "paper",
  discovery: "radar",
};

export function labelOf(key: string): string {
  return NAV.find((n) => n.key === key)?.label ?? key;
}

//: 简单模式只保留这些（主线），其余折叠到"更多功能"
export const SIMPLE_KEYS = ["guide", "lab", "radar", "backtest", "overview"];
