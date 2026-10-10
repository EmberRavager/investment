"""FastAPI 服务：把量化引擎暴露成 API，供前端调用。

启动：
    cd investment
    DEEPSEEK_API_KEY=sk-xxx .venv/bin/uvicorn server.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ashare_pred.config import Config, apply_overrides  # noqa: E402
from ashare_pred.models import list_models  # noqa: E402
from ashare_pred.pipeline import analyze, rank, run, screen  # noqa: E402
from server.reflect import reflect, reflect_panel  # noqa: E402

CONFIG_PATH = os.getenv("ASHARE_CONFIG", str(PROJECT_ROOT / "configs" / "default.yaml"))

#: 选股榜默认股票池（可被请求覆盖）
DEFAULT_UNIVERSE = [
    {"name": "贵州茅台", "symbol": "600519", "kind": "stock"},
    {"name": "宁德时代", "symbol": "300750", "kind": "stock"},
    {"name": "比亚迪", "symbol": "002594", "kind": "stock"},
    {"name": "五粮液", "symbol": "000858", "kind": "stock"},
    {"name": "招商银行", "symbol": "600036", "kind": "stock"},
    {"name": "中国平安", "symbol": "601318", "kind": "stock"},
    {"name": "长江电力", "symbol": "600900", "kind": "stock"},
    {"name": "东方财富", "symbol": "300059", "kind": "stock"},
    {"name": "隆基绿能", "symbol": "601012", "kind": "stock"},
    {"name": "沪深300", "symbol": "000300", "kind": "index"},
]

app = FastAPI(title="A 股量化预测系统 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None      # 完整配置（可选）
    overrides: Optional[Dict[str, Any]] = None   # 点路径覆盖，如 {"backtest.prob_threshold": 0.6}
    persist: bool = False                        # 是否落盘到 outputs


class ReflectRequest(BaseModel):
    summary: Dict[str, Any]
    question: Optional[str] = None
    mode: str = "single"   # single | panel


class RankRequest(BaseModel):
    symbols: Optional[List[Dict[str, Any]]] = None   # 自定义股票池
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


class ScreenRequest(BaseModel):
    top_n: int = 20
    min_amount: float = 1e8
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "config": CONFIG_PATH,
    }


@app.get("/api/models")
def models():
    return {"models": list_models()}


@app.get("/api/default-config")
def default_config():
    return Config.load(CONFIG_PATH).to_dict()


def _build_config(req: RunRequest) -> Config:
    if req.config:
        cfg = Config.from_dict(req.config)
    else:
        cfg = Config.load(CONFIG_PATH)
    if req.overrides:
        # 切换模型但未显式给出参数时，清空上一个模型的遗留参数
        if "model.name" in req.overrides and "model.params" not in req.overrides:
            cfg.model.params = {}
        apply_overrides(cfg, req.overrides)
    return cfg


@app.post("/api/run")
def run_endpoint(req: RunRequest):
    try:
        cfg = _build_config(req)
        if req.persist:
            summary = run(cfg, verbose=True)
            return {"summary": summary}
        return analyze(cfg, verbose=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/screen")
def screen_endpoint(req: ScreenRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
        return screen(cfg, top_n=req.top_n, min_amount=req.min_amount)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/rank")
def rank_endpoint(req: RankRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
        items = req.symbols or DEFAULT_UNIVERSE
        return {"results": rank(cfg, items)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


def _stream(runner):
    """把 runner(progress) 放到线程里执行，以 NDJSON 流式返回进度与最终结果。"""
    q: "queue.Queue" = queue.Queue()

    def worker():
        try:
            result = runner(lambda ev: q.put({"progress": ev}))
            q.put({"done": True, "result": result})
        except Exception as exc:  # noqa: BLE001
            q.put({"error": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    def gen():
        threading.Thread(target=worker, daemon=True).start()
        while True:
            ev = q.get()
            if ev is None:
                break
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/run/stream")
def run_stream(req: RunRequest):
    try:
        cfg = _build_config(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(lambda progress: analyze(cfg, verbose=True, progress=progress))


@app.post("/api/screen/stream")
def screen_stream(req: ScreenRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(
        lambda progress: screen(cfg, top_n=req.top_n, min_amount=req.min_amount, progress=progress)
    )


@app.post("/api/reflect")
def reflect_endpoint(req: ReflectRequest):
    try:
        if req.mode == "panel":
            return {"panel": reflect_panel(req.summary, question=req.question)}
        text = reflect(req.summary, question=req.question)
        return {"reflection": text}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
