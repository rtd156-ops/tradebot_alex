import pytest

from bot.execution.clients import PaperExecution, make_order_link_id


def test_order_link_id_format():
    link = make_order_link_id("conservative", "BTC/USDT")
    assert link.startswith("conserva-BTC-")
    assert len(link) <= 36
    parts = link.split("-")
    assert len(parts) == 4   # estrategia, símbolo, timestamp, uuid


def test_paper_wallet_buy_sell(tmp_path):
    ex = PaperExecution(starting_cash=1000, fee_pct=0.001,
                        wallet_file=str(tmp_path / "wallet.json"))
    fill = ex.market_buy("BTC/USDT", 500, price=50000, order_link_id="x-1")
    assert fill.qty == 0.01
    assert ex.fetch_balances()["USDT"] == pytest.approx(1000 - 500.5)
    assert ex.fetch_balances()["BTC"] == 0.01

    fill = ex.market_sell("BTC/USDT", 0.01, price=55000, order_link_id="x-2")
    assert fill.cost == pytest.approx(550 * 0.999)
    assert "BTC" not in ex.fetch_balances()


def test_paper_wallet_rejects_overdraft(tmp_path):
    ex = PaperExecution(starting_cash=100, fee_pct=0.001,
                        wallet_file=str(tmp_path / "wallet.json"))
    assert ex.market_buy("BTC/USDT", 500, 50000, "x-1") is None
    assert ex.market_sell("BTC/USDT", 0.01, 50000, "x-2") is None


def test_paper_wallet_persists(tmp_path):
    path = str(tmp_path / "wallet.json")
    ex1 = PaperExecution(starting_cash=1000, wallet_file=path)
    ex1.market_buy("ETH/USDT", 200, 2000, "x-1")
    ex2 = PaperExecution(starting_cash=1000, wallet_file=path)
    assert ex2.fetch_balances()["ETH"] == 0.1
