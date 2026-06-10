"""Datos de mercado de criptomonedas desde Bybit (vía ccxt, endpoints públicos).

Si Bybit no responde (p. ej. bloquea la IP del servidor con 403 CloudFront,
común en VPS), cae automáticamente a Yahoo Finance (BTC/USDT -> BTC-USD).
"""
import logging

import ccxt
import pandas as pd

from .history import yahoo_ticker
from .stocks_feed import StocksFeed

log = logging.getLogger(__name__)

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class CryptoFeed:
    def __init__(self):
        self.exchange = ccxt.bybit({"enableRateLimit": True})
        self._fallback = StocksFeed()

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
        """Devuelve velas OHLCV como DataFrame, o None si falla la descarga."""
        try:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if raw:
                df = pd.DataFrame(raw, columns=_COLUMNS)
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                return df
        except Exception as e:
            log.warning("Bybit no disponible para %s (%s); usando Yahoo Finance", symbol, e)
        return self._fallback.get_ohlcv(yahoo_ticker(symbol), timeframe, limit)

    def get_price(self, symbol: str) -> float | None:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            log.warning("Bybit no disponible para %s (%s); usando Yahoo Finance", symbol, e)
        return self._fallback.get_price(yahoo_ticker(symbol))
