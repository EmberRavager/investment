"""集成模型：把多个基模型组合起来（软投票 / Stacking），通常比单模型更稳。

配置示例（YAML / API params）：
    model:
      name: ensemble
      params:
        members: [logistic, xgboost, lightgbm]
        voting: soft            # soft(默认) | hard
        n_jobs: 1               # 并行度（对比时用 1 避免超订）
"""

from __future__ import annotations

from typing import Any, List, Optional

from . import builtin as B
from .base import BaseModel
from .registry import register_model

#: 可作为集成成员的基础模型 -> (工厂函数, 是否需要标准化)
_MEMBERS = {
    "logistic": (B._logistic, True),
    "random_forest": (B._random_forest, False),
    "extra_trees": (B._extra_trees, False),
    "gradient_boosting": (B._gradient_boosting, False),
    "hist_gradient_boosting": (B._hist_gradient_boosting, False),
    "xgboost": (B._xgboost, False),
    "lightgbm": (B._lightgbm, False),
    "svm": (B._svm, True),
    "knn": (B._knn, True),
    "gaussian_nb": (B._gaussian_nb, False),
}

#: 支持 n_jobs 参数的成员
_NJOBS_MEMBERS = {
    "random_forest", "extra_trees", "gradient_boosting",
    "xgboost", "lightgbm", "knn",
}

_DEFAULT_MEMBERS = ["logistic", "xgboost", "lightgbm"]


def _make_member(name: str, n_jobs: int = 1):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if name not in _MEMBERS:
        raise ValueError(f"未知集成成员 '{name}'，可选: {sorted(_MEMBERS)}")
    factory, need_scale = _MEMBERS[name]
    kwargs = {"n_jobs": n_jobs} if name in _NJOBS_MEMBERS else {}
    est = factory(**kwargs)
    if need_scale:
        return Pipeline([("scaler", StandardScaler()), ("clf", est)])
    return est


@register_model("ensemble")
class EnsembleModel(BaseModel):
    """软投票集成：多个模型各给一个概率，加权平均。"""

    def __init__(
        self,
        members: Optional[List[str]] = None,
        voting: str = "soft",
        weights: Optional[List[float]] = None,
        n_jobs: int = -1,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.members = members or list(_DEFAULT_MEMBERS)
        self.voting = voting
        self.weights = weights
        self.n_jobs = n_jobs
        self._clf = None

    def fit(self, X, y):
        from sklearn.ensemble import VotingClassifier

        ests = [(m, _make_member(m, self.n_jobs)) for m in self.members]
        self._clf = VotingClassifier(
            estimators=ests, voting=self.voting, weights=self.weights, n_jobs=self.n_jobs
        )
        self._clf.fit(X, y)
        return self

    def predict_proba(self, X):
        if self._clf is None:
            raise RuntimeError("模型尚未 fit")
        return self._clf.predict_proba(X)


@register_model("stacking")
class StackingModel(BaseModel):
    """Stacking 集成：基模型输出再交给一个「元模型」做最终判断。"""

    def __init__(
        self,
        members: Optional[List[str]] = None,
        meta: str = "logistic",
        cv: int = 3,
        n_jobs: int = -1,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.members = members or list(_DEFAULT_MEMBERS)
        self.meta = meta
        self.cv = cv
        self.n_jobs = n_jobs
        self._clf = None

    def fit(self, X, y):
        from sklearn.ensemble import StackingClassifier

        ests = [(m, _make_member(m, self.n_jobs)) for m in self.members]
        self._clf = StackingClassifier(
            estimators=ests, final_estimator=_make_member(self.meta, self.n_jobs),
            cv=self.cv, n_jobs=self.n_jobs,
        )
        self._clf.fit(X, y)
        return self

    def predict_proba(self, X):
        if self._clf is None:
            raise RuntimeError("模型尚未 fit")
        return self._clf.predict_proba(X)
