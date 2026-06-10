"""Estrategia de señales: combina indicadores técnicos y sentimiento de noticias.

Cada componente aporta un voto entre -1 y 1; el score final ponderado decide
BUY / SELL / HOLD según los umbrales configurados.
"""
import logging
from dataclasses import dataclass

import pandas as pd

from .indicators import macd, rsi, sma

log = logging.getLogger(__name__)


@dataclass
class Signal:
    symbol: str
    action: str          # "BUY" | "SELL" | "HOLD"
    score: float         # score combinado [-1, 1]
    price: float
    details: dict


class Strategy:
    def __init__(self, params: dict):
        self.sma_fast = params.get("sma_fast", 20)
        self.sma_slow = params.get("sma_slow", 50)
        self.rsi_period = params.get("rsi_period", 14)
        self.rsi_oversold = params.get("rsi_oversold", 30)
        self.rsi_overbought = params.get("rsi_overbought", 70)
        self.news_weight = params.get("news_weight", 0.3)
        self.buy_threshold = params.get("buy_threshold", 0.5)
        self.sell_threshold = params.get("sell_threshold", -0.5)

    def technical_score(self, df: pd.DataFrame) -> tuple[float, dict]:
        close = df["close"]
        fast = sma(close, self.sma_fast)
        slow = sma(close, self.sma_slow)
        rsi_now = float(rsi(close, self.rsi_period).iloc[-1])
        macd_line, signal_line = macd(close)

        votes = {}
        # Tendencia: media rápida sobre/bajo la lenta
        votes["sma_cross"] = 1.0 if fast.iloc[-1] > slow.iloc[-1] else -1.0
        # RSI: sobreventa = oportunidad de compra, sobrecompra = venta
        if rsi_now <= self.rsi_oversold:
            votes["rsi"] = 1.0
        elif rsi_now >= self.rsi_overbought:
            votes["rsi"] = -1.0
        else:
            votes["rsi"] = 0.0
        # Momentum MACD
        votes["macd"] = 1.0 if macd_line.iloc[-1] > signal_line.iloc[-1] else -1.0

        score = sum(votes.values()) / len(votes)
        details = {**votes, "rsi_value": round(rsi_now, 1)}
        return score, details

    def generate(self, symbol: str, df: pd.DataFrame, news_sentiment: float = 0.0) -> Signal:
        price = float(df["close"].iloc[-1])
        if len(df) < self.sma_slow + 1:
            return Signal(symbol, "HOLD", 0.0, price, {"error": "histórico insuficiente"})

        tech_score, details = self.technical_score(df)
        combined = (1 - self.news_weight) * tech_score + self.news_weight * news_sentiment
        details["news_sentiment"] = round(news_sentiment, 2)
        details["technical_score"] = round(tech_score, 2)

        if combined >= self.buy_threshold:
            action = "BUY"
        elif combined <= self.sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"

        log.info("%s -> %s (score=%.2f, %s)", symbol, action, combined, details)
        return Signal(symbol, action, round(combined, 3), price, details)
