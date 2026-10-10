"""FastAPI 服务：把量化引擎暴露成 API，供前端调用。

启动：
    cd investment
    DEEPSEEK_API_KEY=sk-xxx .venv/bin/uvicorn server.app:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ashare_pred.config import Config, apply_overrides  # noqa: E402
from ashare_pred.models import list_models  # noqa: E402
from ashare_pred.pipeline import analyze, run  # noqa: E402
from server.reflect import reflect, reflect_panel  # noqa: E402

CONFIG_PATH = os.getenv("ASHARE_CONFIG", str(PROJECT_ROOT / "configs" / "default.yaml"))

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
