"""Datos de mercado de acciones/ETFs e índices desde Yahoo Finance."""
import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Índices de referencia para medir el contexto general del mercado
MARKET_INDICES = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "VIX": "^VIX"}

# yfinance usa intervalos distintos a los timeframes de ccxt
_INTERVAL_MAP = {"15m": "15m", "30m": "30m", "1h": "1h", "4h": "1h", "1d": "1d"}


class StocksFeed:
    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
        interval = _INTERVAL_MAP.get(timeframe, "1h")
        # yfinance limita el histórico intradía; 60 días es el máximo para 1h
        period = "60d" if interval != "1d" else "1y"
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
        except Exception as e:
            log.warning("No se pudieron obtener velas de %s: %s", symbol, e)
            return None
        if df is None or df.empty:
            return None
        df = df.reset_index().rename(
            columns={"Datetime": "timestamp", "Date": "timestamp", "Open": "open",
                     "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        return df[["timestamp", "open", "high", "low", "close", "volume"]].tail(limit).reset_index(drop=True)

    def get_price(self, symbol: str) -> float | None:
        df = self.get_ohlcv(symbol, "1h", limit=2)
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])

    def market_context(self) -> dict:
        """Variación diaria (%) de los índices principales, para contexto de mercado."""
        context = {}
        for name, ticker in MARKET_INDICES.items():
            try:
                closes = yf.Ticker(ticker).history(period="5d", interval="1d")["Close"].dropna()
                if len(closes) >= 2:
                    prev, last = closes.iloc[-2], closes.iloc[-1]
                    context[name] = round(float((last - prev) / prev * 100), 2)
            except Exception as e:
                log.warning("No se pudo obtener el índice %s: %s", name, e)
        return context
