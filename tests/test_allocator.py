import pytest

from bot.allocator import Allocator
from bot.config import StrategyConfig
from bot.ledger import Ledger


def make_strategy(sid="normal", capital=3000, **portfolio):
    base = {"max_position_pct": 0.15, "max_daily_trades": 4}
    base.update(portfolio)
    return StrategyConfig(strategy_id=sid, enabled=True, capital_limit_usd=capital,
                          assets=["BTC/USDT"], strategy={}, portfolio=base)


@pytest.fixture
def setup(tmp_path):
    ledger = Ledger(str(tmp_path / "ledger.sqlite"))
    strat = make_strategy()
    ledger.ensure_strategy(strat.strategy_id, strat.capital_limit_usd)
    return ledger, Allocator(ledger), strat


def test_position_size_is_pct_of_assigned_capital(setup):
    _, allocator, strat = setup
    # 15% de 3000 = 450, hay cash de sobra
    assert allocator.position_size(strat) == pytest.approx(450)


def test_position_size_capped_by_remaining_cash(setup):
    ledger, allocator, strat = setup
    ledger.open_position("normal", "BTC/USDT", 0.05, 50000, 2700, "n-1")
    # Solo quedan 300 de cash: 300*0.98 < 450
    assert allocator.position_size(strat) == pytest.approx(300 * 0.98)


def test_check_buy_happy_path(setup):
    _, allocator, strat = setup
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert ok and reason is None


def test_rejects_duplicate_position(setup):
    ledger, allocator, strat = setup
    ledger.open_position("normal", "BTC/USDT", 0.01, 50000, 500, "n-1")
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert not ok and reason == "position_open"


def test_rejects_daily_limit(setup):
    ledger, allocator, _ = setup
    strat = make_strategy(max_daily_trades=1)
    ledger.open_position("normal", "ETH/USDT", 0.1, 2000, 200, "n-1")
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert not ok and reason == "daily_limit"


def test_rejects_no_capital(setup):
    ledger, allocator, strat = setup
    ledger.open_position("normal", "ETH/USDT", 1, 2000, 2900, "n-1")
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert not ok and reason == "no_capital"


def test_rejects_insufficient_real_balance(setup):
    _, allocator, strat = setup
    # La estrategia tiene cash lógico, pero la wallet real ya no alcanza
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 100)
    assert not ok and reason == "insufficient_real_balance"


def test_rejects_min_order(setup):
    _, allocator, strat = setup
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 5, 0.001, 10000)
    assert not ok and reason == "min_order"


def test_reconcile_ok_with_extra_real_funds(setup):
    ledger, allocator, _ = setup
    ledger.open_position("normal", "BTC/USDT", 0.01, 50000, 500, "n-1")
    problems = allocator.reconcile({"USDT": 50000, "BTC": 0.5})
    assert problems == [] and not allocator.blocked


def test_reconcile_blocks_on_cash_mismatch(setup):
    _, allocator, strat = setup
    # Ledger dice 3000 de cash pero la wallet real solo tiene 100
    problems = allocator.reconcile({"USDT": 100})
    assert problems and allocator.blocked
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 100)
    assert not ok and reason == "balance_mismatch"
    ok, reason = allocator.check_sell(strat, "BTC/USDT")
    assert not ok and reason == "balance_mismatch"


def test_reconcile_blocks_on_coin_mismatch(setup):
    ledger, allocator, _ = setup
    ledger.open_position("normal", "BTC/USDT", 0.05, 50000, 2500, "n-1")
    problems = allocator.reconcile({"USDT": 10000, "BTC": 0.01})
    assert any("BTC" in p for p in problems) and allocator.blocked


def test_reconcile_unblocks_when_fixed(setup):
    _, allocator, strat = setup
    allocator.reconcile({"USDT": 100})
    assert allocator.blocked
    allocator.reconcile({"USDT": 10000})
    assert not allocator.blocked
    ok, _ = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert ok
