# A 股量化预测系统

一个**稳定优先**的 A 股量化研究系统：数据 → 特征 → 可插拔模型 → 严格防前视的滚动回测 →
风控层 → 绩效评估 → React 大盘终端 + DeepSeek 反思机制。

> ⚠️ **诚实声明**：本项目是**研究与决策框架**，不是印钞机。日频价格方向预测极难，
> 开箱的 ML 模型通常没有真实边际（AUC≈0.5）。系统的价值在于**严谨的方法学、风控、
> 可复现的评估**，以及把"模型是否有边际"这件事**诚实地暴露出来**。历史回测不代表未来，
> 不构成任何投资建议。

---

## 一、特性

- **稳定优先的风控层**：趋势过滤 + 波动率目标仓位 + 最少持有期（降换手）+ 回撤熔断。
- **严格防前视**：滚动训练（walk-forward）+ embargo 隔离带，杜绝未来信息泄漏。
- **可插拔模型**：注册表机制，换模型只改配置，不改代码（10 个内置）。
- **可插拔数据源**：`akshare` 直连 / `MCP`（akshare-one-mcp）二选一。
- **实时大盘终端**：React + stock-sdk 实时指数行情 + 净值/概率/特征重要性图表。
- **AI 反思机制**：接入 DeepSeek，单次严格评审 + 多 Agent 辩论式复盘。
- **纯配置驱动**：所有参数集中在 YAML，命令行/API 均可覆盖。

---

## 二、架构

```
config ─┬─► providers/ (akshare | mcp) ─► data.py ─┐
        ├─► features.py / labels.py ──────────────┤
        ├─► models/ (base + registry + builtin) ──┤─► backtest.py ─► metrics.py
        └─► backtest/config ──────────────────────┘        │
                                                          ▼
                                        pipeline.analyze() ─► CLI / FastAPI ─► React
                                                                     │
                                                          server/reflect.py (DeepSeek)
```

单向依赖、无循环。各模块可独立测试与替换。

| 模块 | 职责 |
|---|---|
| `ashare_pred/config.py` | YAML ↔ 数据类，参数校验，点路径覆盖 |
| `ashare_pred/providers/` | 数据源抽象（`base` / `akshare_provider` / `mcp_provider`） |
| `ashare_pred/data.py` | 拉取 + parquet 缓存 + 归一化 |
| `ashare_pred/features.py` | 技术指标特征（基于 `ta` 库，全部因果） |
| `ashare_pred/labels.py` | 未来 N 日涨跌标签 |
| `ashare_pred/models/` | 模型基类 + 注册表 + 内置 sklearn/xgb/lgbm |
| `ashare_pred/backtest.py` | 滚动回测 + 风控层 `build_strategy` |
| `ashare_pred/metrics.py` | 分类指标 + 风险调整收益（夏普/Calmar/回撤） |
| `ashare_pred/pipeline.py` | 编排与输出 |
| `server/app.py` | FastAPI 接口 |
| `server/reflect.py` | DeepSeek 反思（单次 + 多 Agent） |
| `web/` | React 大盘终端 |

---

## 三、安装

```bash
# 1) Python 环境（用 uv 建 3.12，避免新版本轮子缺失）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# macOS 上 xgboost/lightgbm 需要 OpenMP
brew install libomp

# 2) 前端
cd web && npm install && cd ..
```

---

## 四、快速开始

### 1) 命令行

```bash
.venv/bin/python run.py --config configs/default.yaml          # 默认：贵州茅台
.venv/bin/python run.py --model lightgbm --symbol 000300 --kind index
.venv/bin/python run.py --param n_estimators=800 --param max_depth=6
.venv/bin/python run.py --set backtest.prob_threshold=0.6 --set data.provider=mcp
.venv/bin/python run.py --list-models
```

产物写入 `outputs/<dir>/`：`predictions.csv`、`metrics.json`、`feature_importance.csv`、
`report.png`、`result.json`。

### 2) API + 前端

```bash
# 后端（配置 DeepSeek 反思）
DEEPSEEK_API_KEY=sk-xxx .venv/bin/uvicorn server.app:app --port 8000

# 前端
cd web && npm run dev     # http://localhost:5173（/api 已代理到 8000）
```

### 3) 测试

```bash
.venv/bin/pytest -q
```

---

## 五、数据源

两种数据源，配置切换，输出格式统一。

### akshare（默认，直连）

```yaml
data:
  provider: akshare
```

### MCP（akshare-one-mcp）

先起 MCP 服务：

```bash
uvx akshare-one-mcp --streamable-http --port 8081
```

再配置：

```yaml
data:
  provider: mcp
  mcp_url: http://127.0.0.1:8081/mcp
  mcp_tool: get_hist_data       # 换成 ashare-mcp 时用 get_daily_kline
```

> 参考项目：`zwldarren/akshare-one-mcp`、`CharmYue/ashare-mcp`、`aahl/mcp-aktools`、
> `rootSunc/CNEquity`（自托管零 token）。

---

## 六、配置说明（`configs/default.yaml`）

| 段 | 关键项 | 说明 |
|---|---|---|
| `data` | `symbol/kind/start/end/adjust/provider` | 标的与数据源 |
| `features` | `indicators/windows` | 指标族与均线周期 |
| `labels` | `horizon/threshold` | 预测未来 N 日方向 |
| `model` | `name/scale/params` | 模型与超参（`params` 为 JSON/YAML） |
| `backtest` | 见风控层 | 训练窗口/重训频率/风控参数 |
| `backtest.cost` | `commission/stamp_tax/slippage` | A 股交易成本 |
| `output` | `dir/plot/...` | 产物开关 |

### 风控层（稳定优先的核心）

| 参数 | 默认 | 作用 |
|---|---|---|
| `trend_filter` | true | 仅在上行趋势中做多（最有效的稳健过滤） |
| `trend_ma` | 200 | 趋势均线周期 |
| `vol_target` | 0.10 | 年化目标波动率，按已实现波动缩放仓位 |
| `min_hold` | 20 | 最少持有天数，显著降低换手 |
| `drawdown_stop` | 0.15 | 权益回撤熔断阈值 |
| `drawdown_cooldown` | 20 | 熔断后空仓冷却天数 |

---

## 七、扩展模型

两步即可接入新模型：

```python
from ashare_pred.models import register_model, BaseModel

@register_model("my_model")
class MyModel(BaseModel):
    def fit(self, X, y): ...
    def predict_proba(self, X): ...          # 返回 shape=(n,2)
```

然后在 YAML 里把 `model.name` 改成 `my_model` 即可。内置：`logistic` `random_forest`
`extra_trees` `gradient_boosting` `hist_gradient_boosting` `xgboost` `lightgbm`
`svm` `knn` `gaussian_nb`。

---

## 八、AI 反思机制

`server/reflect.py` 把回测结果喂给 DeepSeek，扮演**严格风控评审**：

- **单次评审**：结论 / 是否有边际 / 稳定性风险 / 过拟合陷阱 / 改进建议 / 风险声明。
- **多 Agent 复盘**：风控官、量化研究员、逆向交易员、执行纪律官四视角独立评审，
  再由综合裁判汇总裁决（参考 `2033121/astock-trading-agents` 的辩论+反思闭环）。

前端「AI 反思」面板可切换两种模式，并支持追问。参考项目：`2033121/astock-trading-agents`。

---

## 九、目录

```
investment/
├── ashare_pred/          # 核心引擎（可独立 import）
├── server/               # FastAPI + DeepSeek 反思
├── configs/              # YAML 配置
├── web/                  # React 大盘终端（stock-sdk 实时行情）
├── tests/                # 离线测试
├── run.py                # CLI 入口
├── requirements.txt
└── .env.example
```

---

## 十、免责声明

本项目仅用于技术研究与学习。所有数据版权归原始来源（交易所、东方财富等）。
所有数据与衍生分析**不构成任何投资建议**，据此操作风险自负。
