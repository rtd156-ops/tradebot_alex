from bot.execution.paper import PaperBroker
from bot.risk import RiskManager


def make_broker(tmp_path, cash=1000):
    return PaperBroker(starting_cash=cash, fee_pct=0.001,
                       state_file=str(tmp_path / "state.json"))


def test_buy_and_sell_cycle(tmp_path):
    broker = make_broker(tmp_path)
    assert broker.buy("BTC/USDT", 500, price=100)
    pos = broker.get_position("BTC/USDT")
    assert pos.qty == 5.0
    assert broker.get_cash() < 500  # 500 + comisión descontados

    assert broker.sell("BTC/USDT", price=110)
    assert broker.get_position("BTC/USDT") is None
    assert broker.get_cash() > 1000  # ganancia neta


def test_no_double_buy(tmp_path):
    broker = make_broker(tmp_path)
    assert broker.buy("BTC/USDT", 100, price=100)
    assert not broker.buy("BTC/USDT", 100, price=100)


def test_insufficient_cash(tmp_path):
    broker = make_broker(tmp_path, cash=50)
    assert not broker.buy("BTC/USDT", 100, price=100)


def test_state_persists(tmp_path):
    state_file = str(tmp_path / "state.json")
    b1 = PaperBroker(starting_cash=1000, state_file=state_file)
    b1.buy("ETH/USDT", 200, price=50)
    b2 = PaperBroker(starting_cash=1000, state_file=state_file)
    assert b2.get_position("ETH/USDT").qty == 4.0


def test_risk_exits():
    risk = RiskManager({"stop_loss_pct": 0.05, "take_profit_pct": 0.10})
    assert risk.check_exit(100, 94) == "STOP_LOSS"
    assert risk.check_exit(100, 111) == "TAKE_PROFIT"
    assert risk.check_exit(100, 102) is None
