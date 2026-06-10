"""Indicadores técnicos calculados con pandas (sin dependencias extra)."""
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0):
    """Bandas de Bollinger: (media, banda superior, banda inferior)."""
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return mid, mid + mult * std, mid - mult * std


def donchian(high: pd.Series, low: pd.Series, period_high: int = 20, period_low: int = 10):
    """Canal de Donchian: máximo de N velas y mínimo de M velas, excluyendo
    la vela actual (shift) para detectar rupturas reales."""
    upper = high.rolling(window=period_high).max().shift(1)
    lower = low.rolling(window=period_low).min().shift(1)
    return upper, lower
