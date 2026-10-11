"""Seeded exponential averages: no invented values during the warmup."""
import numpy as np
import pandas as pd


def seeded_average(series: pd.Series, period: int, alpha: float) -> pd.Series:
    output = np.full(len(series), np.nan)
    seed = []
    previous = None
    for index, value in enumerate(series):
        if not np.isfinite(value):
            seed, previous = [], None
            continue
        if previous is None:
            seed.append(float(value))
            if len(seed) < period:
                continue
            previous = float(np.mean(seed))
        else:
            previous += alpha * (float(value) - previous)
        output[index] = previous
    return pd.Series(output, index=series.index)


def wilder(series: pd.Series, period: int = 14) -> pd.Series:
    return seeded_average(series, period, 1.0 / period)


def ema(series: pd.Series, period: int) -> pd.Series:
    return seeded_average(series, period, 2.0 / (period + 1))


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain, loss = wilder(delta.clip(lower=0), period), wilder(-delta.clip(upper=0), period)
    value = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    value = value.mask((loss == 0) & (gain > 0), 100)
    return value.mask((gain == 0) & (loss == 0), 50)
