import pytest

from bot.ledger import Ledger


@pytest.fixture
def ledger(tmp_path):
    return Ledger(str(tmp_path / "ledger.sqlite"))


def test_ensure_strategy_initializes_cash(ledger):
    ledger.ensure_strategy("conservative", 2000)
    assert ledger.cash("conservative") == 2000
    assert ledger.capital_limit("conservative") == 2000


def test_capital_change_adjusts_cash(ledger):
    ledger.ensure_strategy("normal", 3000)
    ledger.ensure_strategy("normal", 3500)   # subió el límite
    assert ledger.cash("normal") == 3500
    ledger.ensure_strategy("normal", 3000)   # bajó
    assert ledger.cash("normal") == 3000


def test_open_close_cycle_and_cash_accounting(ledger):
    ledger.ensure_strategy("normal", 3000)
    ledger.open_position("normal", "BTC/USDT", qty=0.01, entry_price=50000,
                         cost=500.5, order_link_id="normal-BTC-1-aaa")
    assert ledger.cash("normal") == pytest.approx(2499.5)
    pos = ledger.position("normal", "BTC/USDT")
    assert pos["qty"] == 0.01

    pnl = ledger.close_position("normal", "BTC/USDT", exit_price=55000,
                                proceeds=549.45, reason="take_profit",
                                order_link_id="normal-BTC-2-bbb")
    assert pnl == pytest.approx(48.95)
    assert ledger.position("normal", "BTC/USDT") is None
    assert ledger.cash("normal") == pytest.approx(3048.95)
    trades = ledger.trades("normal")
    assert len(trades) == 1 and trades[0]["reason"] == "take_profit"


def test_cannot_overspend(ledger):
    ledger.ensure_strategy("conservative", 100)
    with pytest.raises(ValueError):
        ledger.open_position("conservative", "BTC/USDT", 0.01, 50000, 500, "x-1")


def test_positions_isolated_per_strategy(ledger):
    ledger.ensure_strategy("a", 1000)
    ledger.ensure_strategy("b", 1000)
    ledger.open_position("a", "BTC/USDT", 0.01, 50000, 500, "a-1")
    assert ledger.position("b", "BTC/USDT") is None
    assert ledger.total_qty_by_symbol() == {"BTC/USDT": 0.01}
    ledger.open_position("b", "BTC/USDT", 0.02, 50000, 999, "b-1")
    assert ledger.total_qty_by_symbol()["BTC/USDT"] == pytest.approx(0.03)
    # La venta de 'a' no toca la posición de 'b'
    ledger.close_position("a", "BTC/USDT", 51000, 509, "signal", "a-2")
    assert ledger.position("b", "BTC/USDT")["qty"] == 0.02


def test_state_survives_reopen(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    l1 = Ledger(path)
    l1.ensure_strategy("normal", 3000)
    l1.open_position("normal", "ETH/USDT", 0.5, 2000, 1001, "n-1")
    l1.close()
    l2 = Ledger(path)
    assert l2.cash("normal") == pytest.approx(1999)
    assert l2.position("normal", "ETH/USDT")["qty"] == 0.5


def test_signals_and_rejects_recorded(ledger):
    ledger.ensure_strategy("agg", 5000)
    ledger.record_signal("agg", "BTC/USDT", "BUY", 0.6, 50000, True)
    ledger.record_signal("agg", "BTC/USDT", "BUY", 0.7, 50000, False, "daily_limit")
    ledger.record_signal("agg", "BTC/USDT", "HOLD", 0.1, 50000, False)
    assert ledger.signal_counts("agg") == {"BUY": 2, "HOLD": 1}
    assert ledger.reject_counts("agg") == {"daily_limit": 1}


def test_buys_today(ledger):
    ledger.ensure_strategy("normal", 3000)
    assert ledger.buys_today("normal") == 0
    ledger.open_position("normal", "BTC/USDT", 0.01, 50000, 500, "n-1")
    assert ledger.buys_today("normal") == 1
