from bot.config import Config

BASE = """
mode: paper
interval_minutes: 15
portfolio:
  max_position_pct: 0.15
  stop_loss_pct: 0.05
notifications:
  telegram: false
  webhook: false
"""

LOCAL = """
mode: live
notifications:
  webhook: true
"""


def test_local_config_overrides_base(tmp_path):
    (tmp_path / "config.yaml").write_text(BASE, encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text(LOCAL, encoding="utf-8")
    config = Config.load(str(tmp_path / "config.yaml"))
    # Sobrescritos por el local
    assert config.mode == "live"
    assert config.notifications["webhook"] is True
    # Heredados del base (merge profundo, no reemplazo del bloque completo)
    assert config.notifications["telegram"] is False
    assert config.portfolio["stop_loss_pct"] == 0.05
    assert config.interval_minutes == 15


def test_without_local_config(tmp_path):
    (tmp_path / "config.yaml").write_text(BASE, encoding="utf-8")
    config = Config.load(str(tmp_path / "config.yaml"))
    assert config.mode == "paper"
    assert config.notifications["webhook"] is False
