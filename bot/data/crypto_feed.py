"""Datos de mercado de criptomonedas desde Bybit (vía ccxt, endpoints públicos)."""
import logging

import ccxt
import pandas as pd

log = logging.getLogger(__name__)

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class CryptoFeed:
    def __init__(self):
        self.exchange = ccxt.bybit({"enableRateLimit": True})

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
        """Devuelve velas OHLCV como DataFrame, o None si falla la descarga."""
        try:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            log.warning("No se pudieron obtener velas de %s: %s", symbol, e)
            return None
        if not raw:
            return None
        df = pd.DataFrame(raw, columns=_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def get_price(self, symbol: str) -> float | None:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            log.warning("No se pudo obtener el precio de %s: %s", symbol, e)
            return None
