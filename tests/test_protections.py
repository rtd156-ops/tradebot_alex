"""Pruebas de P1 (trailing stop, cooldown) y P2 (stoploss guard, max drawdown)."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from bot.allocator import Allocator
from bot.config import StrategyConfig
from bot.ledger import Ledger
from bot.risk import RiskManager


def iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def insert_trade(ledger, sid, symbol, pnl, reason, closed_minutes_ago):
    ledger.conn.execute(
        "INSERT INTO trades(strategy_id,symbol,qty,entry_price,exit_price,pnl,"
        "reason,opened_at,closed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, symbol, 1, 100, 100 + pnl, pnl, reason,
         iso(closed_minutes_ago + 60), iso(closed_minutes_ago)))
    ledger.conn.commit()


def make_strategy(**portfolio):
    base = {"max_position_pct": 0.15, "max_daily_trades": 10}
    base.update(portfolio)
    return StrategyConfig(strategy_id="normal", enabled=True, capital_limit_usd=3000,
                          assets=["BTC/USDT"], strategy={}, portfolio=base)


@pytest.fixture
def ledger(tmp_path):
    led = Ledger(str(tmp_path / "ledger.sqlite"))
    led.ensure_strategy("normal", 3000)
    return led


# --- Trailing stop (RiskManager) ---

def test_trailing_not_active_below_offset():
    risk = RiskManager({"trailing_stop": True, "trailing_stop_positive": 0.02,
                        "trailing_stop_positive_offset": 0.03,
                        "stop_loss_pct": 0.05, "take_profit_pct": 0.10})
    # Pico a +2% (< offset de 3%): el trailing no aplica aunque caiga del pico
    assert risk.check_exit(100, 100.1, peak_price=102) is None


def test_trailing_locks_in_profit():
    risk = RiskManager({"trailing_stop": True, "trailing_stop_positive": 0.02,
                        "trailing_stop_positive_offset": 0.03,
                        "stop_loss_pct": 0.05, "take_profit_pct": 0.50})
    # Pico a +6%: trailing activo a 106*0.98=103.88
    assert risk.check_exit(100, 103.5, peak_price=106) == "TRAILING_STOP"
    assert risk.check_exit(100, 104.5, peak_price=106) is None


def test_static_stops_still_work_with_trailing_enabled():
    risk = RiskManager({"trailing_stop": True, "stop_loss_pct": 0.05,
                        "take_profit_pct": 0.10})
    assert risk.check_exit(100, 94, peak_price=101) == "STOP_LOSS"
    assert risk.check_exit(100, 111, peak_price=111) == "TAKE_PROFIT"


def test_no_trailing_when_disabled():
    risk = RiskManager({"trailing_stop": False, "stop_loss_pct": 0.05,
                        "take_profit_pct": 0.50})
    assert risk.check_exit(100, 103.5, peak_price=106) is None


# --- Peak tracking (Ledger) ---

def test_peak_price_tracks_maximum(ledger):
    ledger.open_position("normal", "BTC/USDT", 0.01, 100, 1.001, "n-1")
    assert ledger.position("normal", "BTC/USDT")["peak_price"] == 100
    ledger.update_peak("normal", "BTC/USDT", 110)
    ledger.update_peak("normal", "BTC/USDT", 105)   # no debe bajar
    assert ledger.position("normal", "BTC/USDT")["peak_price"] == 110


def test_migration_adds_peak_column(tmp_path):
    path = str(tmp_path / "old.sqlite")
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE positions(
        strategy_id TEXT NOT NULL, symbol TEXT NOT NULL, qty REAL NOT NULL,
        entry_price REAL NOT NULL, cost REAL NOT NULL, order_link_id TEXT,
        opened_at TEXT NOT NULL, PRIMARY KEY(strategy_id, symbol))""")
    conn.execute("INSERT INTO positions VALUES ('normal','BTC/USDT',0.01,100,100.1,'x','2026-01-01')")
    conn.commit()
    conn.close()
    ledger = Ledger(path)   # debe migrar sin romper la fila existente
    pos = ledger.position("normal", "BTC/USDT")
    assert pos["peak_price"] == 100


# --- Cooldown ---

def test_cooldown_blocks_rebuy(ledger):
    strat = make_strategy(cooldown_minutes=120)
    allocator = Allocator(ledger)
    insert_trade(ledger, "normal", "BTC/USDT", -5, "stop_loss", closed_minutes_ago=30)
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert not ok and reason == "cooldown"
    # Otro símbolo no está en cooldown
    ok, _ = allocator.check_buy(strat, "ETH/USDT", 450, 0.001, 10000)
    assert ok


def test_cooldown_expires(ledger):
    strat = make_strategy(cooldown_minutes=120)
    allocator = Allocator(ledger)
    insert_trade(ledger, "normal", "BTC/USDT", -5, "stop_loss", closed_minutes_ago=180)
    ok, _ = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert ok


# --- Stoploss guard ---

def test_stoploss_guard_pauses_entries(ledger):
    strat = make_strategy(stoploss_guard_limit=3,
                          stoploss_guard_lookback_minutes=1440,
                          stoploss_guard_stop_minutes=720, cooldown_minutes=0)
    allocator = Allocator(ledger)
    for ago in (300, 200, 100):
        insert_trade(ledger, "normal", "XRP/USDT", -10, "stop_loss", ago)
    ok, reason = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert not ok and reason == "stoploss_guard"
    # Las salidas NO se bloquean por guards
    ledger.open_position("normal", "BTC/USDT", 0.01, 100, 1.001, "n-9")
    ok, _ = allocator.check_sell(strat, "BTC/USDT")
    assert ok


def test_stoploss_guard_releases_after_stop_duration(ledger):
    strat = make_strategy(stoploss_guard_limit=3,
                          stoploss_guard_lookback_minutes=2880,
                          stoploss_guard_stop_minutes=60, cooldown_minutes=0)
    allocator = Allocator(ledger)
    for ago in (400, 300, 200):   # el último stop fue hace 200 min > 60 de pausa
        insert_trade(ledger, "normal", "XRP/USDT", -10, "stop_loss", ago)
    ok, _ = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert ok


def test_take_profits_do_not_trigger_guard(ledger):
    strat = make_strategy(stoploss_guard_limit=2, cooldown_minutes=0)
    allocator = Allocator(ledger)
    for ago in (300, 200, 100):
        insert_trade(ledger, "normal", "XRP/USDT", 20, "take_profit", ago)
    ok, _ = allocator.check_buy(strat, "BTC/USDT", 450, 0.001, 10000)
    assert ok


# --- Max drawdown ---

def test_max_drawdown_pauses_entries(ledger):
    strat = make_strategy(max_drawdown_pct=0.10, drawdown_lookback_minutes=10080,
                          cooldown_minutes=0, stoploss_guard_limit=0)
    allocator = Allocator(ledger)
    # +200 de pico y luego -550: drawdown 550/3000 = 18% > 10%
    insert_trade(ledger, "normal", "BTC/USDT", 200, "take_profit", 500)
    insert_trade(ledger, "normal", "XRP/USDT", -300, "stop_loss", 400)
    insert_trade(ledger, "normal", "BNB/USDT", -250, "stop_loss", 300)
    ok, reason = allocator.check_buy(strat, "ETH/USDT", 450, 0.001, 10000)
    assert not ok and reason == "max_drawdown"


def test_drawdown_outside_window_ignored(ledger):
    strat = make_strategy(max_drawdown_pct=0.10, drawdown_lookback_minutes=60,
                          cooldown_minutes=0, stoploss_guard_limit=0)
    allocator = Allocator(ledger)
    insert_trade(ledger, "normal", "XRP/USDT", -600, "stop_loss", 600)   # fuera de la ventana
    ok, _ = allocator.check_buy(strat, "ETH/USDT", 450, 0.001, 10000)
    assert ok
