"""模型子包：导入即完成内置模型注册。"""

from .base import BaseModel
from .registry import (
    build_model,
    get_model_class,
    list_models,
    register_external,
    register_model,
)
from . import builtin  # noqa: F401  触发内置模型注册
from . import ensemble  # noqa: F401  触发集成模型注册

__all__ = [
    "BaseModel",
    "build_model",
    "get_model_class",
    "list_models",
    "register_external",
    "register_model",
]
