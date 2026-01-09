# services/ai/metrics.py
from __future__ import annotations
from typing import List
import math


def mae(y_true: List[float], y_pred: List[float]) -> float:
    if not y_true or not y_pred:
        return 0.0
    n = min(len(y_true), len(y_pred))
    if n <= 0:
        return 0.0
    return sum(abs(y_true[i] - y_pred[i]) for i in range(n)) / n


def rmse(y_true: List[float], y_pred: List[float]) -> float:
    if not y_true or not y_pred:
        return 0.0
    n = min(len(y_true), len(y_pred))
    if n <= 0:
        return 0.0
    return math.sqrt(sum((y_true[i] - y_pred[i]) ** 2 for i in range(n)) / n)


def mape(y_true: List[float], y_pred: List[float]) -> float:
    if not y_true or not y_pred:
        return 0.0
    n = min(len(y_true), len(y_pred))
    if n <= 0:
        return 0.0
    eps = 1e-6
    return sum(abs((y_true[i] - y_pred[i]) / (y_true[i] + eps)) for i in range(n)) * 100.0 / n
