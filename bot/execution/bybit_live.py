"""Broker real sobre Bybit spot (vía ccxt). Solo opera criptomonedas.

ADVERTENCIA: este broker mueve dinero real. Úsalo únicamente después de
validar la estrategia en modo paper, y empieza con BYBIT_TESTNET=true.
"""
import logging

import ccxt

from .base import Broker, Position

log = logging.getLogger(__name__)


class BybitLiveBroker(Broker):
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        if not api_key or not api_secret:
            raise ValueError(
                "Faltan BYBIT_API_KEY / BYBIT_API_SECRET en el .env para el modo live"
            )
        self.exchange = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)
            log.info("Bybit en modo TESTNET")
        # Precio de entrada por símbolo (en memoria; Bybit spot no lo guarda)
        self._entries: dict[str, float] = {}

    def buy(self, symbol: str, usd_amount: float, price: float) -> bool:
        try:
            qty = usd_amount / price
            order = self.exchange.create_market_buy_order(symbol, qty)
            self._entries[symbol] = float(order.get("average") or price)
            log.info("[LIVE] COMPRA %s: %s", symbol, order["id"])
            return True
        except Exception as e:
            log.error("Error al comprar %s: %s", symbol, e)
            return False

    def sell(self, symbol: str, price: float) -> bool:
        pos = self.get_position(symbol)
        if not pos or pos.qty <= 0:
            return False
        try:
            order = self.exchange.create_market_sell_order(symbol, pos.qty)
            self._entries.pop(symbol, None)
            log.info("[LIVE] VENTA %s: %s", symbol, order["id"])
            return True
        except Exception as e:
            log.error("Error al vender %s: %s", symbol, e)
            return False

    def get_position(self, symbol: str) -> Position | None:
        base = symbol.split("/")[0]
        try:
            balance = self.exchange.fetch_balance()
            qty = float(balance.get(base, {}).get("free") or 0)
        except Exception as e:
            log.error("Error al consultar balance de %s: %s", base, e)
            return None
        if qty <= 0:
            return None
        return Position(symbol, qty, self._entries.get(symbol, 0.0))

    def get_cash(self) -> float:
        try:
            balance = self.exchange.fetch_balance()
            return float(balance.get("USDT", {}).get("free") or 0)
        except Exception as e:
            log.error("Error al consultar efectivo: %s", e)
            return 0.0

    def portfolio_value(self, prices: dict[str, float]) -> float:
        value = self.get_cash()
        for symbol, price in prices.items():
            pos = self.get_position(symbol)
            if pos:
                value += pos.qty * price
        return value
