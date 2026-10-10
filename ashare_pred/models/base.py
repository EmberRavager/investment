"""模型基类：任何模型只要实现 fit / predict_proba 即可接入，无需改动流水线。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np


class BaseModel(ABC):
    """所有预测模型的统一接口。

    子类必须实现 fit 与 predict_proba；predict 默认取概率 0.5 阈值。
    """

    #: 注册名，用于配置文件里的 model.name
    name: str = "base"

    def __init__(self, **params: Any) -> None:
        self.params: Dict[str, Any] = dict(params)

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseModel":
        ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """返回 shape=(n, 2) 的概率，第 1 列为正类概率。"""
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)[:, 1]
        return (proba >= 0.5).astype(int)

    @property
    def feature_importances_(self) -> Optional[np.ndarray]:
        return None
