import numpy as np
import pandas as pd

from bot.backtest import run_backtest

PARAMS = {"news_weight": 0.0, "sma_fast": 20, "sma_slow": 50}
RISK = {"stop_loss_pct": 0.05, "take_profit_pct": 0.10}


def make_df(prices):
    arr = np.array(prices, dtype=float)
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=len(arr), freq="D"),
        "open": arr, "high": arr * 1.005, "low": arr * 0.995,
        "close": arr, "volume": [100] * len(arr),
    })


def cycle_prices(n=300):
    # Mercado con ciclos alcistas/bajistas y ruido: genera operaciones
    x = np.arange(n)
    return 100 + 30 * np.sin(x / 25) + x * 0.1 + 5 * np.sin(x / 3)


def test_backtest_produces_trades_and_sane_metrics():
    result = run_backtest("TEST", make_df(cycle_prices()), PARAMS, RISK)
    assert result.trades > 0
    assert 0.0 <= result.win_rate <= 1.0
    assert result.max_drawdown_pct <= 0.0
    assert len(result.trade_log) == result.trades


def test_backtest_short_history_returns_empty():
    result = run_backtest("TEST", make_df([100] * 20), PARAMS, RISK)
    assert result.trades == 0


def test_stop_loss_limits_single_trade_loss():
    result = run_backtest("TEST", make_df(cycle_prices()), PARAMS,
                          {"stop_loss_pct": 0.05, "take_profit_pct": 0.10})
    # Ninguna operación debe perder mucho más que el stop (5%) + comisiones
    assert all(t["ret_pct"] >= -6.0 for t in result.trade_log)
