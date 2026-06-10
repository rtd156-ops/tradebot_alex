"""Broker simulado (paper trading). Persiste el estado en un archivo JSON
para que el portafolio sobreviva reinicios del bot."""
import json
import logging
import os
from datetime import datetime, timezone

from .base import Broker, Position

log = logging.getLogger(__name__)

STATE_FILE = "data/state/paper_portfolio.json"


class PaperBroker(Broker):
    def __init__(self, starting_cash: float = 10000, fee_pct: float = 0.001,
                 state_file: str = STATE_FILE):
        self.fee_pct = fee_pct
        self.state_file = state_file
        self.state = self._load() or {
            "cash": starting_cash,
            "positions": {},   # symbol -> {qty, entry_price}
            "history": [],
        }

    def _load(self) -> dict | None:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("No se pudo leer el estado previo: %s", e)
        return None

    def _save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _record(self, action: str, symbol: str, qty: float, price: float, pnl: float | None = None):
        self.state["history"].append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action": action, "symbol": symbol,
            "qty": qty, "price": price, "pnl": pnl,
        })

    def buy(self, symbol: str, usd_amount: float, price: float) -> bool:
        if symbol in self.state["positions"]:
            log.info("Ya hay posición abierta en %s, no se compra de nuevo", symbol)
            return False
        cost = usd_amount * (1 + self.fee_pct)
        if cost > self.state["cash"]:
            log.info("Efectivo insuficiente para comprar %s (%.2f USD)", symbol, cost)
            return False
        qty = usd_amount / price
        self.state["cash"] -= cost
        self.state["positions"][symbol] = {"qty": qty, "entry_price": price}
        self._record("BUY", symbol, qty, price)
        self._save()
        log.info("[PAPER] COMPRA %s: %.6f @ %.2f (%.2f USD)", symbol, qty, price, usd_amount)
        return True

    def sell(self, symbol: str, price: float) -> bool:
        pos = self.state["positions"].get(symbol)
        if not pos:
            return False
        proceeds = pos["qty"] * price * (1 - self.fee_pct)
        pnl = proceeds - pos["qty"] * pos["entry_price"]
        self.state["cash"] += proceeds
        del self.state["positions"][symbol]
        self._record("SELL", symbol, pos["qty"], price, round(pnl, 2))
        self._save()
        log.info("[PAPER] VENTA %s: %.6f @ %.2f (PnL: %+.2f USD)", symbol, pos["qty"], price, pnl)
        return True

    def get_position(self, symbol: str) -> Position | None:
        pos = self.state["positions"].get(symbol)
        if not pos:
            return None
        return Position(symbol, pos["qty"], pos["entry_price"])

    def get_cash(self) -> float:
        return self.state["cash"]

    def portfolio_value(self, prices: dict[str, float]) -> float:
        value = self.state["cash"]
        for symbol, pos in self.state["positions"].items():
            price = prices.get(symbol, pos["entry_price"])
            value += pos["qty"] * price
        return value

    def trades_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for t in self.state["history"]
                   if t["action"] == "BUY" and t["time"].startswith(today))
