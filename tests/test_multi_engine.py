"""Integración del MultiEngine con feed y noticias falsos (sin red)."""
import numpy as np
import pandas as pd
import pytest

from bot.config import Config
from bot.execution.clients import PaperExecution
from bot.ledger import Ledger
from bot.multi_engine import MultiEngine

YAML = """
mode: paper
paper_starting_cash: 10000
assets:
  crypto: [BTC/USDT]
portfolio:
  fee_pct: 0.001
  max_position_pct: 0.15
  stop_loss_pct: 0.05
  take_profit_pct: 0.10
  max_daily_trades: 4
strategy:
  sma_fast: 20
  sma_slow: 50
  rsi_period: 14
  buy_threshold: 0.5
  sell_threshold: -0.5
  news_weight: 0.0
news:
  enabled: false
notifications: {}
multi_strategy:
  enabled: true
  strategies:
    conservative:
      capital_limit_usd: 2000
      portfolio: {max_position_pct: 0.08}
    aggressive:
      capital_limit_usd: 5000
      portfolio: {max_position_pct: 0.25}
      strategy: {buy_threshold: 0.35}
"""


class FakeFeed:
    """Velas sintéticas: tendencia alcista con oscilación -> señal BUY."""
    def __init__(self):
        n = 120
        base = np.linspace(100, 200, n) + 10 * np.sin(np.arange(n) / 2)
        self.df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
            "open": base, "high": base, "low": base, "close": base,
            "volume": [100] * n,
        })

    def get_ohlcv(self, symbol, timeframe, limit):
        return self.df


@pytest.fixture
def engine(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(YAML, encoding="utf-8")
    config = Config.load(str(config_path))
    ledger = Ledger(str(tmp_path / "ledger.sqlite"))
    execution = PaperExecution(starting_cash=10000, fee_pct=0.001,
                               wallet_file=str(tmp_path / "wallet.json"))
    eng = MultiEngine(config, ledger=ledger, execution=execution)
    eng.feed = FakeFeed()
    return eng


def test_both_strategies_buy_with_own_capital(engine):
    engine.run_cycle()
    pos_cons = engine.ledger.position("conservative", "BTC/USDT")
    pos_aggr = engine.ledger.position("aggressive", "BTC/USDT")
    assert pos_cons is not None and pos_aggr is not None
    # Cada una usó SU capital: 8% de 2000 = 160; 25% de 5000 = 1250
    assert pos_cons["cost"] == pytest.approx(160 * 1.001, rel=1e-6)
    assert pos_aggr["cost"] == pytest.approx(1250 * 1.001, rel=1e-6)
    # La wallet compartida refleja ambas compras
    assert engine.execution.fetch_balances()["USDT"] == pytest.approx(
        10000 - 160 * 1.001 - 1250 * 1.001)


def test_second_cycle_rejects_duplicate(engine):
    engine.run_cycle()
    engine.run_cycle()   # misma señal BUY, ya hay posición
    rejects = engine.ledger.reject_counts("aggressive")
    assert rejects.get("position_open") == 1
    # Sigue habiendo exactamente UNA posición por estrategia
    assert len(engine.ledger.positions("aggressive")) == 1


def test_mismatch_blocks_trading(engine):
    # Vacía la wallet real sin tocar el ledger -> divergencia
    engine.execution.wallet = {"USDT": 1.0}
    engine.execution._save()
    engine.run_cycle()
    assert engine.allocator.blocked
    assert engine.ledger.position("conservative", "BTC/USDT") is None
    rejects = engine.ledger.reject_counts("conservative")
    assert rejects.get("balance_mismatch") == 1
