"""Descarga de velas históricas: intenta Bybit y cae a Yahoo Finance."""
import logging

import pandas as pd

log = logging.getLogger(__name__)

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def yahoo_ticker(symbol: str) -> str:
    """'BTC/USDT' -> 'BTC-USD' (mapeo genérico para cripto en Yahoo)."""
    return f"{symbol.split('/')[0]}-USD"


def fetch_daily(symbol: str, days: int = 365) -> pd.DataFrame | None:
    try:
        import ccxt
        raw = ccxt.bybit({"enableRateLimit": True}).fetch_ohlcv(symbol, "1d", limit=days)
        if raw:
            df = pd.DataFrame(raw, columns=_COLUMNS)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            return df
    except Exception as e:
        log.debug("Bybit no disponible para %s (%s), probando Yahoo", symbol, e)
    try:
        import yfinance as yf
        hist = yf.Ticker(yahoo_ticker(symbol)).history(period=f"{days}d", interval="1d")
        if hist is None or hist.empty:
            return None
        df = hist.reset_index().rename(columns={
            "Date": "timestamp", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"})
        return df[_COLUMNS]
    except Exception as e:
        log.warning("Sin datos históricos para %s: %s", symbol, e)
        return None
