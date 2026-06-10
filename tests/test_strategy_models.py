import numpy as np
import pandas as pd
import pytest

from bot.strategy.models import (BreakoutStrategy, MeanReversionStrategy,
                                 build_strategy)
from bot.strategy.strategy import Strategy


def make_df(prices, highs=None, lows=None):
    arr = np.array(prices, dtype=float)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(arr), freq="h"),
        "open": arr,
        "high": np.array(highs, dtype=float) if highs is not None else arr,
        "low": np.array(lows, dtype=float) if lows is not None else arr,
        "close": arr, "volume": [100] * len(arr),
    })


# --- Factory ---

def test_factory_selects_models():
    assert isinstance(build_strategy({}), Strategy)
    assert isinstance(build_strategy({"signal_model": "trend"}), Strategy)
    assert isinstance(build_strategy({"signal_model": "mean_reversion"}),
                      MeanReversionStrategy)
    assert isinstance(build_strategy({"signal_model": "breakout"}), BreakoutStrategy)
    with pytest.raises(ValueError):
        build_strategy({"signal_model": "no_existe"})


def test_all_models_expose_min_candles():
    for model in ("trend", "mean_reversion", "breakout"):
        assert build_strategy({"signal_model": model}).min_candles > 0


# --- Mean reversion ---

def test_meanrev_buys_panic_dip():
    # Mercado oscilando suave alrededor de 100 y desplome final a 90:
    # precio < banda inferior y RSI en sobreventa
    prices = list(100 + 2 * np.sin(np.arange(40) / 3)) + [97, 95, 92, 90]
    signal = MeanReversionStrategy({"news_weight": 0.0}).generate("TEST", make_df(prices))
    assert signal.action == "BUY"


def test_meanrev_sells_recovery_to_mean():
    # Caída y rebote de vuelta a la media: toma la ganancia
    prices = list(100 + 2 * np.sin(np.arange(40) / 3)) + [92, 90, 95, 100, 101]
    signal = MeanReversionStrategy({"news_weight": 0.0}).generate("TEST", make_df(prices))
    assert signal.action == "SELL"


def test_meanrev_holds_mid_range():
    prices = list(100 + 2 * np.sin(np.arange(40) / 3)) + [98.5]
    signal = MeanReversionStrategy({"news_weight": 0.0}).generate("TEST", make_df(prices))
    assert signal.action == "HOLD"


def test_meanrev_short_history_holds():
    signal = MeanReversionStrategy({}).generate("TEST", make_df([100] * 10))
    assert signal.action == "HOLD"


# --- Breakout ---

def test_breakout_buys_new_high_in_uptrend():
    # Tendencia alcista y última vela rompe el máximo de las 20 previas
    prices = list(np.linspace(100, 120, 60)) + [125]
    signal = BreakoutStrategy({"news_weight": 0.0}).generate("TEST", make_df(prices))
    assert signal.action == "BUY"


def test_breakout_sells_breakdown():
    # Rango y desplome bajo el mínimo de 10 velas, bajo la SMA de tendencia
    prices = list(100 + 2 * np.sin(np.arange(60) / 3)) + [90]
    signal = BreakoutStrategy({"news_weight": 0.0}).generate("TEST", make_df(prices))
    assert signal.action == "SELL"


def test_breakout_ignores_countertrend_breakout():
    # Ruptura de máximos pero AÚN bajo la SMA50 (rebote en tendencia bajista):
    # el filtro de tendencia la descarta
    prices = list(np.linspace(150, 100, 55)) + [104, 105, 106, 107, 108]
    df = make_df(prices)
    signal = BreakoutStrategy({"news_weight": 0.0}).generate("TEST", df)
    assert signal.action == "HOLD"
