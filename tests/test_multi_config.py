from bot.config import Config

YAML = """
mode: paper
assets:
  crypto: [BTC/USDT, XRP/USDT]
portfolio:
  max_position_pct: 0.15
  stop_loss_pct: 0.05
  fee_pct: 0.001
strategy:
  sma_fast: 20
  sma_slow: 50
  buy_threshold: 0.5
  news_weight: 0.3
multi_strategy:
  enabled: true
  strategies:
    conservative:
      enabled: true
      capital_limit_usd: 2000
      portfolio:
        max_position_pct: 0.08
      strategy:
        buy_threshold: 0.65
    disabled_one:
      enabled: false
      capital_limit_usd: 999
    aggressive:
      capital_limit_usd: 5000
      assets: [BNB/USDT]
      strategy:
        sma_fast: 10
"""


def make(tmp_path):
    (tmp_path / "config.yaml").write_text(YAML, encoding="utf-8")
    return Config.load(str(tmp_path / "config.yaml"))


def test_enabled_flag(tmp_path):
    config = make(tmp_path)
    assert config.multi_strategy_enabled
    ids = [s.strategy_id for s in config.strategies()]
    assert ids == ["conservative", "aggressive"]   # la deshabilitada no aparece


def test_overrides_merge_over_base(tmp_path):
    config = make(tmp_path)
    cons = next(s for s in config.strategies() if s.strategy_id == "conservative")
    # Override aplicado
    assert cons.portfolio["max_position_pct"] == 0.08
    assert cons.strategy["buy_threshold"] == 0.65
    # Heredados del bloque base
    assert cons.portfolio["stop_loss_pct"] == 0.05
    assert cons.strategy["sma_slow"] == 50
    assert cons.strategy["news_weight"] == 0.3
    # Assets por defecto = assets.crypto
    assert cons.assets == ["BTC/USDT", "XRP/USDT"]


def test_custom_assets_and_capital(tmp_path):
    config = make(tmp_path)
    agg = next(s for s in config.strategies() if s.strategy_id == "aggressive")
    assert agg.assets == ["BNB/USDT"]
    assert agg.capital_limit_usd == 5000
    assert agg.strategy["sma_fast"] == 10
    assert agg.strategy["sma_slow"] == 50   # heredado


def test_base_config_not_mutated_by_strategy_merge(tmp_path):
    config = make(tmp_path)
    config.strategies()
    assert config.strategy["buy_threshold"] == 0.5
    assert config.portfolio["max_position_pct"] == 0.15


def test_disabled_multi(tmp_path):
    (tmp_path / "config.yaml").write_text(
        YAML.replace("enabled: true", "enabled: false", 1), encoding="utf-8")
    config = Config.load(str(tmp_path / "config.yaml"))
    assert not config.multi_strategy_enabled
