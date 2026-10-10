"""模型注册表：把名字映射到模型类，配置驱动构建，插件式扩展。

扩展新模型只需两步：
    1. 继承 BaseModel 实现 fit / predict_proba；
    2. 用 @register_model("名字") 装饰，或调用 register_model 手动注册。
之后在 YAML 里把 model.name 改成该名字即可，无需改动任何其它代码。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Type

from .base import BaseModel

_REGISTRY: Dict[str, Type[BaseModel]] = {}


def register_model(name: str) -> Callable[[Type[BaseModel]], Type[BaseModel]]:
    def deco(cls: Type[BaseModel]) -> Type[BaseModel]:
        if name in _REGISTRY:
            raise ValueError(f"模型名重复: {name}")
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get_model_class(name: str) -> Type[BaseModel]:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的模型 '{name}'。可用: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def build_model(name: str, **params: Any) -> BaseModel:
    return get_model_class(name)(**params)


def list_models() -> List[str]:
    return sorted(_REGISTRY)


def register_external(name: str, cls: Type[BaseModel]) -> None:
    """供外部脚本注册自定义模型类。"""
    register_model(name)(cls)
