"""Analiza una canasta de criptomonedas y recomienda las mejores para operar.

Para cada candidata calcula:
  - Score técnico de la estrategia del bot (SMA/RSI/MACD) sobre velas diarias
  - Momentum: retornos a 30 y 90 días
  - Volatilidad anualizada (30 días) — informativa, penaliza levemente
  - Sentimiento de noticias (mismo módulo del bot)

Score final = 0.45*técnico + 0.30*momentum + 0.15*noticias - 0.10*exceso de volatilidad

Intenta descargar datos de Bybit; si no hay acceso, usa Yahoo Finance.

Uso:  python scripts/recommend.py [--top 3]
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from bot.config import Config
from bot.data.news_feed import NewsFeed
from bot.strategy.strategy import Strategy

# Pares spot líquidos disponibles en Bybit (y su ticker en Yahoo Finance)
CANDIDATES = {
    "BTC/USDT": "BTC-USD",
    "ETH/USDT": "ETH-USD",
    "SOL/USDT": "SOL-USD",
    "BNB/USDT": "BNB-USD",
    "XRP/USDT": "XRP-USD",
    "ADA/USDT": "ADA-USD",
    "AVAX/USDT": "AVAX-USD",
    "LINK/USDT": "LINK-USD",
    "DOGE/USDT": "DOGE-USD",
    "DOT/USDT": "DOT-USD",
}


def fetch_daily(symbol: str, yahoo_ticker: str, days: int = 200) -> pd.DataFrame | None:
    try:
        import ccxt
        raw = ccxt.bybit({"enableRateLimit": True}).fetch_ohlcv(symbol, "1d", limit=days)
        if raw:
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        hist = yf.Ticker(yahoo_ticker).history(period=f"{days}d", interval="1d")
        if hist is None or hist.empty:
            return None
        df = hist.reset_index().rename(columns={
            "Date": "timestamp", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"})
        return df[["timestamp", "open", "high", "low", "close", "volume"]]
    except Exception:
        return None


def analyze(top_n: int):
    config = Config.load(str(Path(__file__).resolve().parent.parent / "config.yaml"))
    strategy = Strategy(config.strategy)
    news = NewsFeed(config.news.get("feeds", []), config.news.get("max_headlines", 60))

    rows = []
    for symbol, yahoo in CANDIDATES.items():
        df = fetch_daily(symbol, yahoo)
        if df is None or len(df) < 91:
            print(f"  (sin datos suficientes para {symbol}, se omite)")
            continue
        close = df["close"]
        sentiment = news.sentiment_for(symbol)
        signal = strategy.generate(symbol, df, sentiment)
        tech = signal.details.get("technical_score", 0.0)

        ret30 = float(close.iloc[-1] / close.iloc[-31] - 1)
        ret90 = float(close.iloc[-1] / close.iloc[-91] - 1)
        vol30 = float(close.pct_change().tail(30).std() * math.sqrt(365))

        momentum = max(-1.0, min(1.0, ret30 / 0.20))          # ±20% en 30d = ±1
        vol_excess = max(0.0, min(1.0, (vol30 - 0.50) / 0.50))  # >50% anual penaliza
        score = 0.45 * tech + 0.30 * momentum + 0.15 * sentiment - 0.10 * vol_excess

        rows.append({
            "símbolo": symbol, "precio": round(float(close.iloc[-1]), 4),
            "score": round(score, 3), "técnico": round(tech, 2),
            "ret_30d_%": round(ret30 * 100, 1), "ret_90d_%": round(ret90 * 100, 1),
            "volatilidad_%": round(vol30 * 100, 0), "noticias": round(sentiment, 2),
            "RSI": signal.details.get("rsi_value"), "señal_bot": signal.action,
        })

    if not rows:
        print("No se pudieron descargar datos de ninguna candidata.")
        return

    table = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    table.index += 1
    print("\n=== Ranking de candidatas (velas diarias) ===\n")
    print(table.to_string())
    print(f"\n=== Top {top_n} recomendadas para la prueba ===")
    for _, row in table.head(top_n).iterrows():
        print(f"  {row['símbolo']:10s} score {row['score']:+.3f} | "
              f"30d {row['ret_30d_%']:+.1f}% | RSI {row['RSI']} | noticias {row['noticias']:+.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=3)
    analyze(parser.parse_args().top)
