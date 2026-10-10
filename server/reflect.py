"""反思层：单次严格评审 + 多 Agent 辩论式复盘（参考 astock-trading-agents 的反思闭环）。

DeepSeek 使用 OpenAI 兼容接口，配置环境变量：
    DEEPSEEK_API_KEY=sk-xxx
    DEEPSEEK_BASE_URL=https://api.deepseek.com   (可选)
    DEEPSEEK_MODEL=deepseek-chat                  (可选)
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """你是一位极其严谨、以风险控制为第一优先的资深量化交易员与模型评审。
你的职责不是吹捧收益，而是冷静地找出这套策略的缺陷、数据陷阱和过拟合风险。

评审时严格遵循：
1. 诚实优先：宁可指出策略没有边际，也不要为了好看而粉饰。
2. 稳定优先：相对于高收益，更看重低回撤、正夏普、可复现性。
3. 定量：引用给出的具体数字（准确率、AUC、基准上涨率、夏普、Calmar、最大回撤）。
4. 具体：改进建议必须可执行、可检验，不要空话。

请严格按以下 Markdown 结构输出（中文）：
## 一、结论
用一句话给出：这套策略当前【可用 / 需改进 / 不可用】，并说明理由。
## 二、模型是否有真实边际
对比准确率/AUC 与基准上涨率，判断是否优于随机；指出 AUC<0.5 或≈0.5 的含义。
## 三、稳定性与风险
评价夏普、Calmar、最大回撤、持仓占比、换手；指出回撤熔断/趋势过滤是否在起作用。
## 四、过拟合与数据陷阱
指出前视偏差、幸存者偏差、样本外退化、超参过拟合等可能风险。
## 五、可执行的改进建议
给出 3-6 条具体建议，按对稳定性提升的优先级排序。
## 六、风险声明
一句话提醒：历史回测不代表未来，本分析不构成投资建议。
"""

#: 多 Agent 复盘面板：每个视角独立评审，最后综合
PANEL: List[Dict[str, str]] = [
    {"name": "风控官", "focus": "只关注回撤、波动率、仓位与熔断机制是否可靠，指出极端行情下的尾部风险"},
    {"name": "量化研究员", "focus": "只关注模型是否存在真实统计边际、是否过拟合、样本外是否退化"},
    {"name": "逆向交易员", "focus": "假设这套策略是错的，找出最可能让它持续亏钱的市场环境与失效条件"},
    {"name": "执行/纪律官", "focus": "只关注换手率、交易成本、滑点与心理层面，判断能否被长期纪律性执行"},
]


def _compact(summary: Dict[str, Any]) -> Dict[str, Any]:
    cfg = summary.get("config", {})
    return {
        "标的": summary.get("symbol"),
        "类别": summary.get("kind"),
        "模型": summary.get("model"),
        "特征数": summary.get("n_features"),
        "最新信号": {"日期": summary.get("last_date"),
                     "多头概率": summary.get("last_prob"),
                     "信号": summary.get("signal")},
        "分类指标": summary.get("metrics", {}).get("classification", {}),
        "策略指标": summary.get("metrics", {}).get("strategy", {}),
        "基准指标": summary.get("metrics", {}).get("benchmark", {}),
        "特征重要性Top10": dict(list(summary.get("feature_importance", {}).items())[:10]),
        "关键配置": {
            "标签": cfg.get("labels"),
            "风控": {k: v for k, v in cfg.get("backtest", {}).items() if k != "cost"},
            "模型参数": cfg.get("model", {}).get("params"),
        },
    }


def _chat(messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
    import httpx

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY 环境变量，无法调用反思模型")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=120) as client:
        resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek 调用失败 {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def reflect(summary: Dict[str, Any], question: Optional[str] = None) -> str:
    """单次严格评审。"""
    payload = json.dumps(_compact(summary), ensure_ascii=False, indent=2)
    user = f"以下是一次 A 股量化策略的回测结果，请进行严格评审与反思：\n\n```json\n{payload}\n```"
    if question:
        user += f"\n\n另外，用户追问：{question}"
    return _chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])


def reflect_panel(summary: Dict[str, Any], question: Optional[str] = None) -> Dict[str, str]:
    """多 Agent 辩论式复盘：各视角独立评审后综合。返回 {视角名: 文本}。"""
    base = json.dumps(_compact(summary), ensure_ascii=False, indent=2)
    tail = f"\n\n用户追问：{question}" if question else ""

    def one(agent: Dict[str, str]) -> tuple[str, str]:
        msgs = [
            {"role": "system",
             "content": f"你是这场量化策略评审会上的「{agent['name']}」。你的职责视角：{agent['focus']}。"
                        f"只从你的视角出发，输出 3-5 条要点，中文，简洁，必须引用给出的具体数字，不要客套。"},
            {"role": "user", "content": f"策略回测结果：\n```json\n{base}\n```{tail}"},
        ]
        return agent["name"], _chat(msgs, temperature=0.4)

    results: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(PANEL)) as ex:
        for name, text in ex.map(one, PANEL):
            results[name] = text

    # 综合裁判
    synth_user = (
        f"策略回测结果：\n```json\n{base}\n```\n\n"
        f"各位评审意见：\n" + json.dumps(results, ensure_ascii=False, indent=2) + tail
    )
    results["综合裁决"] = _chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": synth_user},
    ])
    return results


def build_messages(summary: Dict[str, Any], question: Optional[str] = None):
    """保留给测试/调试。"""
    payload = json.dumps(_compact(summary), ensure_ascii=False, indent=2)
    user = f"以下是一次 A 股量化策略的回测结果：\n\n```json\n{payload}\n```"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
