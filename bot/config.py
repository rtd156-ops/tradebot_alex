"""Carga de configuración desde config.yaml y variables de entorno (.env).

Si junto a config.yaml existe un config.local.yaml (ignorado por git), sus
valores se aplican encima: ahí van los ajustes propios de cada máquina
(p. ej. mode o notifications.webhook en el VPS) sin que un git pull los pise.
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@dataclass
class StrategyConfig:
    """Configuración resuelta de una estrategia del modo multi-estrategia."""
    strategy_id: str
    enabled: bool
    capital_limit_usd: float
    assets: list
    strategy: dict   # parámetros de señal (sma, rsi, umbrales, news_weight...)
    portfolio: dict  # parámetros de riesgo (max_position_pct, stops, límites...)


@dataclass
class Config:
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = "config.yaml") -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        local_path = Path(path).with_name("config.local.yaml")
        if local_path.exists():
            with open(local_path, "r", encoding="utf-8") as f:
                local = yaml.safe_load(f) or {}
            _deep_merge(raw, local)
            log.info("Aplicada configuración local: %s", local_path)
        return cls(raw=raw)

    @property
    def mode(self) -> str:
        return self.raw.get("mode", "paper")

    @property
    def interval_minutes(self) -> int:
        return int(self.raw.get("interval_minutes", 15))

    @property
    def paper_starting_cash(self) -> float:
        return float(self.raw.get("paper_starting_cash", 10000))

    @property
    def portfolio(self) -> dict:
        return self.raw.get("portfolio", {})

    @property
    def crypto_symbols(self) -> list:
        return self.raw.get("assets", {}).get("crypto", [])

    @property
    def stock_symbols(self) -> list:
        return self.raw.get("assets", {}).get("stocks", [])

    @property
    def strategy(self) -> dict:
        return self.raw.get("strategy", {})

    @property
    def news(self) -> dict:
        return self.raw.get("news", {})

    @property
    def notifications(self) -> dict:
        return self.raw.get("notifications", {})

    # --- Multi-estrategia ---
    @property
    def multi_strategy_enabled(self) -> bool:
        return bool(self.raw.get("multi_strategy", {}).get("enabled", False))

    def strategies(self) -> list[StrategyConfig]:
        """Estrategias habilitadas, con los bloques base 'strategy' y
        'portfolio' del YAML como defaults y los overrides aplicados encima."""
        result = []
        defined = self.raw.get("multi_strategy", {}).get("strategies", {}) or {}
        for sid, spec in defined.items():
            spec = spec or {}
            if not spec.get("enabled", True):
                continue
            strategy_params = _deep_merge(dict(self.strategy), dict(spec.get("strategy", {}) or {}))
            portfolio_params = _deep_merge(dict(self.portfolio), dict(spec.get("portfolio", {}) or {}))
            result.append(StrategyConfig(
                strategy_id=sid,
                enabled=True,
                capital_limit_usd=float(spec.get("capital_limit_usd", 0)),
                assets=list(spec.get("assets", self.crypto_symbols)),
                strategy=strategy_params,
                portfolio=portfolio_params,
            ))
        return result

    # --- Credenciales (solo desde variables de entorno, nunca del YAML) ---
    @property
    def bybit_api_key(self) -> str:
        return os.getenv("BYBIT_API_KEY", "")

    @property
    def bybit_api_secret(self) -> str:
        return os.getenv("BYBIT_API_SECRET", "")

    @property
    def bybit_testnet(self) -> bool:
        return os.getenv("BYBIT_TESTNET", "true").lower() in ("1", "true", "yes")

    @property
    def telegram_token(self) -> str:
        return os.getenv("TELEGRAM_BOT_TOKEN", "")

    @property
    def telegram_chat_id(self) -> str:
        return os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def webhook_url(self) -> str:
        return os.getenv("WEBHOOK_URL", "")

    @property
    def webhook_token(self) -> str:
        return os.getenv("WEBHOOK_TOKEN", "")
