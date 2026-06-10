import numpy as np
import pandas as pd

from bot.strategy.indicators import rsi, sma
from bot.strategy.strategy import Strategy


def make_df(prices):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(prices), freq="h"),
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [100] * len(prices),
    })


def test_sma():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 5).iloc[-1] == 3.0


def test_rsi_range():
    prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
    values = rsi(prices, 14).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def trend_with_noise(start, end, n=120):
    # Oscilación sobre la tendencia para que el RSI no quede en extremos.
    # El signo del ruido sigue a la tendencia para que el tramo final
    # acompañe la dirección y el caso bajista sea espejo del alcista.
    direction = 1 if end > start else -1
    base = np.linspace(start, end, n)
    return list(base + direction * 10 * np.sin(np.arange(n) / 2))


def test_uptrend_generates_buy():
    # Tendencia alcista con RSI neutral: SMA y MACD votan a comprar
    signal = Strategy({"news_weight": 0.0, "buy_threshold": 0.5}).generate(
        "TEST", make_df(trend_with_noise(100, 200)))
    assert signal.action == "BUY"


def test_downtrend_generates_sell():
    signal = Strategy({"news_weight": 0.0, "sell_threshold": -0.5}).generate(
        "TEST", make_df(trend_with_noise(200, 100)))
    assert signal.action == "SELL"


def test_overbought_uptrend_holds():
    # Subida lineal sin pausa: el RSI en sobrecompra frena la compra
    signal = Strategy({"news_weight": 0.0}).generate(
        "TEST", make_df(list(np.linspace(100, 200, 120))))
    assert signal.action == "HOLD"


def test_short_history_holds():
    signal = Strategy({}).generate("TEST", make_df([100.0] * 10))
    assert signal.action == "HOLD"
