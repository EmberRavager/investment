"""内置模型：全部通过注册表接入，配置里用 model.name 选择。

默认参数只是起点，配置里的 model.params 会覆盖它们。
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .base import BaseModel
from .registry import register_model

# --------------------------------------------------------------------------- #
# 通用 sklearn 包装器
# --------------------------------------------------------------------------- #


class SklearnClassifier(BaseModel):
    """把任意 sklearn 风格分类器包装成 BaseModel。

    子类只需提供 _factory（一个返回 estimator 的可调用对象）。
    scale=True 时自动前置 StandardScaler，适合逻辑回归 / SVM / KNN 等。
    """

    _factory: Callable[..., Any] = None  # type: ignore

    def __init__(self, scale: bool = False, **params: Any) -> None:
        super().__init__(**params)
        self.scale = scale
        self._pipeline = None

    def _make_estimator(self):
        return self._factory(**self.params)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SklearnClassifier":
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        steps = []
        if self.scale:
            steps.append(("scaler", StandardScaler()))
        steps.append(("clf", self._make_estimator()))
        self._pipeline = Pipeline(steps)
        self._pipeline.fit(X, y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._pipeline is None:
            raise RuntimeError("模型尚未 fit")
        return self._pipeline.predict_proba(X)

    @property
    def feature_importances_(self):
        if self._pipeline is None:
            return None
        clf = self._pipeline.named_steps["clf"]
        return getattr(clf, "feature_importances_", None)


# --------------------------------------------------------------------------- #
# 工厂函数
# --------------------------------------------------------------------------- #


def _logistic(**p):
    from sklearn.linear_model import LogisticRegression

    params = dict(max_iter=2000, C=1.0)
    params.update(p)
    return LogisticRegression(**params)


def _random_forest(**p):
    from sklearn.ensemble import RandomForestClassifier

    params = dict(n_estimators=400, max_depth=6, min_samples_leaf=20,
                  n_jobs=-1, random_state=42)
    params.update(p)
    return RandomForestClassifier(**params)


def _extra_trees(**p):
    from sklearn.ensemble import ExtraTreesClassifier

    params = dict(n_estimators=400, max_depth=8, min_samples_leaf=20,
                  n_jobs=-1, random_state=42)
    params.update(p)
    return ExtraTreesClassifier(**params)


def _gradient_boosting(**p):
    from sklearn.ensemble import GradientBoostingClassifier

    params = dict(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=42)
    params.update(p)
    return GradientBoostingClassifier(**params)


def _hist_gradient_boosting(**p):
    from sklearn.ensemble import HistGradientBoostingClassifier

    params = dict(max_iter=300, max_depth=4, learning_rate=0.05, random_state=42)
    params.update(p)
    return HistGradientBoostingClassifier(**params)


def _xgboost(**p):
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:  # pragma: no cover
        raise ImportError("使用 xgboost 需要先安装: pip install xgboost") from exc

    params = dict(n_estimators=400, max_depth=4, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
                  tree_method="hist", n_jobs=-1, random_state=42)
    params.update(p)
    return XGBClassifier(**params)


def _lightgbm(**p):
    try:
        from lightgbm import LGBMClassifier
    except ImportError as exc:  # pragma: no cover
        raise ImportError("使用 lightgbm 需要先安装: pip install lightgbm") from exc

    params = dict(n_estimators=400, num_leaves=31, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                  random_state=42, verbose=-1)
    params.update(p)
    return LGBMClassifier(**params)


def _svm(**p):
    from sklearn.svm import SVC

    params = dict(probability=True, C=1.0, gamma="scale", random_state=42)
    params.update(p)
    return SVC(**params)


def _knn(**p):
    from sklearn.neighbors import KNeighborsClassifier

    params = dict(n_neighbors=15, n_jobs=-1)
    params.update(p)
    return KNeighborsClassifier(**params)


def _gaussian_nb(**p):
    from sklearn.naive_bayes import GaussianNB

    params = dict()
    params.update(p)
    return GaussianNB(**params)


# --------------------------------------------------------------------------- #
# 注册
# --------------------------------------------------------------------------- #


@register_model("logistic")
class LogisticModel(SklearnClassifier):
    _factory = staticmethod(_logistic)


@register_model("random_forest")
class RandomForestModel(SklearnClassifier):
    _factory = staticmethod(_random_forest)


@register_model("extra_trees")
class ExtraTreesModel(SklearnClassifier):
    _factory = staticmethod(_extra_trees)


@register_model("gradient_boosting")
class GradientBoostingModel(SklearnClassifier):
    _factory = staticmethod(_gradient_boosting)


@register_model("hist_gradient_boosting")
class HistGradientBoostingModel(SklearnClassifier):
    _factory = staticmethod(_hist_gradient_boosting)


@register_model("xgboost")
class XGBoostModel(SklearnClassifier):
    _factory = staticmethod(_xgboost)


@register_model("lightgbm")
class LightGBMModel(SklearnClassifier):
    _factory = staticmethod(_lightgbm)


@register_model("svm")
class SVMModel(SklearnClassifier):
    _factory = staticmethod(_svm)


@register_model("knn")
class KNNModel(SklearnClassifier):
    _factory = staticmethod(_knn)


@register_model("gaussian_nb")
class GaussianNBModel(SklearnClassifier):
    _factory = staticmethod(_gaussian_nb)
