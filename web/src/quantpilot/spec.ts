// 平台默认策略配置（结构，不是演示数据）。全部分布式来自后端计算。
export const DEFAULT_SPEC = {
  name: "成长趋势跟随",
  universe: ["600519", "000858", "600036", "601318", "600900", "300750", "002594", "000001"],
  filters: [{ field: "ma20", op: ">", value: "ma60" }],
  entry: [
    { field: "close", op: ">", value: "ma20" },
    { field: "vol_ratio", op: ">", value: 1.3 },
  ],
  exit: [{ field: "close", op: "<", value: "ma20" }],
  weight: 0.3,
  max_position_per_stock: 0.3,
  stop_loss: 0.08,
  drawdown_stop: 0.15,
  drawdown_cooldown: 20,
};

export const DEFAULT_CASH = 100000;
