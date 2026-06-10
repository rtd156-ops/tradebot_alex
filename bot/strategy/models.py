"""Modelos de señal intercambiables para el modo multi-estrategia.

Cada estrategia elige su modelo con `signal_model` en su bloque `strategy`:

- "trend" (default): seguimiento de tendencia con SMA + RSI + MACD (la
  Strategy original).
- "mean_reversion": reversión a la media con Bandas de Bollinger + RSI.
  Compra el pánico (precio bajo la banda inferior con RSI en sobreventa)
  y vende el rebote (precio de vuelta en la media).
- "breakout": ruptura de canal de Donchian (estilo Turtle Traders) con
  filtro de tendencia SMA. Compra rupturas de máximos de N velas a favor
  de tendencia; sale cuando el precio pierde el mínimo de M velas.

Todos comparten la interfaz: generate(symbol, df, news_sentiment) -> Signal,
combinan su score técnico con noticias vía news_weight y exponen
min_candles (histórico mínimo necesario).
"""
import logging

import pandas as pd

from .indicators import bollinger, donchian, rsi, sma
from .strategy import Signal, Strategy

log = logging.getLogger(__name__)


class MeanReversionStrategy:
    def __init__(self, params: dict):
        self.bb_period = params.get("bb_period", 20)
        self.bb_mult = params.get("bb_mult", 2.0)
        self.rsi_period = params.get("rsi_period", 14)
        self.rsi_oversold = params.get("rsi_oversold", 35)
        self.rsi_overbought = params.get("rsi_overbought", 65)
        self.news_weight = params.get("news_weight", 0.2)
        self.buy_threshold = params.get("buy_threshold", 0.5)
        self.sell_threshold = params.get("sell_threshold", -0.5)
        self.min_candles = max(self.bb_period, self.rsi_period) + 5

    def generate(self, symbol: str, df: pd.DataFrame, news_sentiment: float = 0.0) -> Signal:
        price = float(df["close"].iloc[-1])
        if len(df) < self.min_candles:
            return Signal(symbol, "HOLD", 0.0, price, {"error": "histórico insuficiente"})
        close = df["close"]
        mid, _, lower = bollinger(close, self.bb_period, self.bb_mult)
        rsi_now = float(rsi(close, self.rsi_period).iloc[-1])

        # La banda pesa doble: es la condición principal del modelo
        if price <= float(lower.iloc[-1]):
            bb_vote = 1.0       # pánico: precio fuera de la banda inferior
        elif price >= float(mid.iloc[-1]):
            bb_vote = -1.0      # rebote completado: de vuelta en la media
        else:
            bb_vote = 0.0
        if rsi_now <= self.rsi_oversold:
            rsi_vote = 1.0
        elif rsi_now >= self.rsi_overbought:
            rsi_vote = -1.0
        else:
            rsi_vote = 0.0
        tech = (2 * bb_vote + rsi_vote) / 3
        combined = (1 - self.news_weight) * tech + self.news_weight * news_sentiment

        if combined >= self.buy_threshold:
            action = "BUY"
        elif combined <= self.sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
        details = {"model": "mean_reversion", "bb_vote": bb_vote,
                   "rsi_value": round(rsi_now, 1), "technical_score": round(tech, 2),
                   "news_sentiment": round(news_sentiment, 2)}
        log.info("%s -> %s (score=%.2f, %s)", symbol, action, combined, details)
        return Signal(symbol, action, round(combined, 3), price, details)


class BreakoutStrategy:
    def __init__(self, params: dict):
        self.period_high = params.get("donchian_high", 20)
        self.period_low = params.get("donchian_low", 10)
        self.trend_sma = params.get("trend_sma", 50)
        self.news_weight = params.get("news_weight", 0.2)
        self.buy_threshold = params.get("buy_threshold", 0.5)
        self.sell_threshold = params.get("sell_threshold", -0.5)
        self.min_candles = max(self.period_high, self.trend_sma) + 5

    def generate(self, symbol: str, df: pd.DataFrame, news_sentiment: float = 0.0) -> Signal:
        price = float(df["close"].iloc[-1])
        if len(df) < self.min_candles:
            return Signal(symbol, "HOLD", 0.0, price, {"error": "histórico insuficiente"})
        upper, lower = donchian(df["high"], df["low"], self.period_high, self.period_low)
        trend = float(sma(df["close"], self.trend_sma).iloc[-1])

        if price > float(upper.iloc[-1]):
            breakout_vote = 1.0     # ruptura de máximos de N velas
        elif price < float(lower.iloc[-1]):
            breakout_vote = -1.0    # pérdida de mínimos de M velas
        else:
            breakout_vote = 0.0
        trend_vote = 1.0 if price > trend else -1.0
        # La ruptura pesa doble; el filtro de tendencia evita rupturas falsas
        tech = (2 * breakout_vote + trend_vote) / 3
        combined = (1 - self.news_weight) * tech + self.news_weight * news_sentiment

        if combined >= self.buy_threshold:
            action = "BUY"
        elif combined <= self.sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
        details = {"model": "breakout", "breakout_vote": breakout_vote,
                   "trend_vote": trend_vote, "technical_score": round(tech, 2),
                   "news_sentiment": round(news_sentiment, 2)}
        log.info("%s -> %s (score=%.2f, %s)", symbol, action, combined, details)
        return Signal(symbol, action, round(combined, 3), price, details)


MODELS = {
    "trend": Strategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout": BreakoutStrategy,
}


def build_strategy(params: dict):
    """Crea el modelo de señal según params['signal_model'] (default: trend)."""
    model = params.get("signal_model", "trend")
    if model not in MODELS:
        raise ValueError(f"signal_model desconocido: '{model}' (opciones: {list(MODELS)})")
    return MODELS[model](params)
