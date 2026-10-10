"""配置系统：YAML -> 数据类，全局可调，不写死任何参数。"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _build(cls, raw: Dict[str, Any]):
    """按数据类字段过滤未知键，避免 YAML 里多写字段直接报错。"""
    if raw is None:
        raw = {}
    valid = {f.name for f in fields(cls)}
    unknown = set(raw) - valid
    if unknown:
        raise ValueError(f"{cls.__name__} 收到未知配置项: {sorted(unknown)}")
    return cls(**raw)


@dataclass
class DataConfig:
    symbol: str = "600519"          # 股票/指数代码，纯数字
    kind: str = "stock"             # stock | index
    market: str = "sh"              # index 时用于拼接，如 sh000001 -> 000001
    start: str = "2018-01-01"
    end: str = ""                   # 留空 = 到今天（始终包含最新数据）
    adjust: str = "qfq"             # qfq(前复权) | hfq | ""(不复权)
    cache_dir: str = "data/cache"
    use_cache: bool = True
    provider: str = "akshare"       # akshare | mcp
    # MCP 数据源配置（provider=mcp 时生效）
    mcp_url: str = "http://127.0.0.1:8081/mcp"
    mcp_tool: str = "get_hist_data"  # akshare-one-mcp 用 get_hist_data；ashare-mcp 用 get_daily_kline
    mcp_recent_n: int = 100000       # 只保留最近 N 条（确保覆盖所需区间）


@dataclass
class FeatureConfig:
    # 使用的技术指标族，取自 ta 库；可在 YAML 中自由增删
    indicators: List[str] = field(
        default_factory=lambda: [
            "returns", "sma", "ema", "rsi", "macd",
            "atr", "bollinger", "obv", "roc", "volume",
        ]
    )
    windows: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    dropna: bool = True             # 生成特征后是否丢弃含 NaN 的行


@dataclass
class LabelConfig:
    horizon: int = 1                # 预测未来 N 根 K 线的方向
    threshold: float = 0.0          # 收益率超过该阈值判为 1(上涨)
    method: str = "direction"       # direction(涨跌分类) | return(回归，暂未用于分类模型)


@dataclass
class ModelConfig:
    name: str = "xgboost"           # 注册表里的模型名，见 ashare_pred.models.list_models()
    params: Dict[str, Any] = field(default_factory=dict)
    scale: bool = False             # 是否对特征做标准化（线性/距离类模型建议 true）


@dataclass
class CostConfig:
    commission: float = 0.00025     # 佣金（双边）
    stamp_tax: float = 0.0005       # 印花税（仅卖出）
    slippage: float = 0.0005        # 滑点


@dataclass
class BacktestConfig:
    train_window: int = 500         # 滚动训练窗口（根）
    min_train: int = 250            # 首次开始交易前的最小训练样本数
    retrain_every: int = 20         # 每隔多少根 K 线重新训练
    embargo: int = 0                # 训练集与测试集之间的隔离带，0 表示自动取 horizon
    prob_threshold: float = 0.55    # 预测概率高于该值才开仓(做多)
    # ---- 稳定优先的风控层 ----
    trend_filter: bool = True       # 仅在上行趋势中做多（最有效的稳健过滤）
    trend_ma: int = 120             # 趋势均线周期
    vol_target: float = 0.12        # 年化目标波动率（0 表示不做波动率目标）
    vol_lookback: int = 20          # 计算已实现波动率的窗口
    max_position: float = 1.0       # 仓位上限
    min_hold: int = 10              # 最少持有天数，显著降低换手
    drawdown_stop: float = 0.15     # 权益回撤超过该值触发熔断（0 表示关闭）
    drawdown_cooldown: int = 20     # 熔断后空仓冷却天数
    cost: CostConfig = field(default_factory=CostConfig)


@dataclass
class OutputConfig:
    dir: str = "outputs"
    plot: bool = True
    save_predictions: bool = True
    save_model: bool = True


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Config":
        raw = raw or {}
        cfg = cls(
            data=_build(DataConfig, raw.get("data")),
            features=_build(FeatureConfig, raw.get("features")),
            labels=_build(LabelConfig, raw.get("labels")),
            model=_build(ModelConfig, raw.get("model")),
            backtest=_build(BacktestConfig, raw.get("backtest")),
            output=_build(OutputConfig, raw.get("output")),
        )
        if isinstance(raw.get("backtest"), dict) and "cost" in raw["backtest"]:
            cfg.backtest.cost = _build(CostConfig, raw["backtest"]["cost"])
        # 结束日期留空/写"今天" => 取今天，保证包含最新数据
        if not cfg.data.end or str(cfg.data.end).lower() in ("today", "now", "今天"):
            cfg.data.end = datetime.date.today().isoformat()
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.labels.horizon < 1:
            raise ValueError("labels.horizon 必须 >= 1")
        # 隔离带至少要等于预测跨度，否则训练集最后一个样本的标签会用掉测试期的价格
        if self.backtest.embargo < self.labels.horizon:
            self.backtest.embargo = self.labels.horizon

    def resolved_embargo(self) -> int:
        return max(self.backtest.embargo, self.labels.horizon)

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def apply_overrides(cfg: Config, overrides: Dict[str, Any]) -> Config:
    """按点路径覆盖配置，例如 {"backtest.prob_threshold": 0.6}。"""
    for dotted, value in (overrides or {}).items():
        keys = dotted.split(".")
        cur: Any = cfg
        for k in keys[:-1]:
            cur = getattr(cur, k)
        setattr(cur, keys[-1], value)
    cfg.validate()
    return cfg
