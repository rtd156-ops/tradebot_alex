"""Noticias financieras vía RSS y análisis de sentimiento por léxico de palabras clave.

El sentimiento se calcula contando palabras alcistas/bajistas en los titulares
relevantes para cada activo. Devuelve un score entre -1 (muy negativo) y +1
(muy positivo). Es un enfoque simple pero sin dependencias externas ni API keys.
"""
import logging
import time

import feedparser

log = logging.getLogger(__name__)

BULLISH = {
    "surge", "rally", "soar", "soars", "jump", "jumps", "gain", "gains", "record",
    "high", "bullish", "rebound", "recover", "recovery", "boost", "growth", "beat",
    "beats", "upgrade", "upgraded", "outperform", "buy", "adoption", "approval",
    "approved", "breakthrough", "profit", "profits", "strong", "rises", "rise",
    "sube", "alza", "récord", "gana", "ganancias", "crecimiento", "optimista",
}
BEARISH = {
    "crash", "plunge", "plunges", "fall", "falls", "drop", "drops", "slump", "fear",
    "bearish", "sell-off", "selloff", "loss", "losses", "downgrade", "downgraded",
    "lawsuit", "hack", "hacked", "fraud", "ban", "banned", "recession", "inflation",
    "warning", "weak", "miss", "misses", "decline", "declines", "tumble", "tumbles",
    "cae", "caída", "desploma", "pérdidas", "fraude", "demanda", "recesión",
}

# Palabras clave para asociar titulares con cada activo
ASSET_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth "],
    "SOL": ["solana"],
    "AAPL": ["apple", "aapl", "iphone"],
    "MSFT": ["microsoft", "msft"],
    "NVDA": ["nvidia", "nvda"],
    "SPY": ["s&p", "sp500", "stocks", "wall street", "fed "],
}


def _score_text(text: str) -> int:
    words = text.lower().replace(",", " ").split()
    score = 0
    lower = text.lower()
    for w in words:
        if w in BULLISH:
            score += 1
        elif w in BEARISH:
            score -= 1
    # Frases compuestas que el split por palabras no captura
    for phrase in ("all-time high", "máximo histórico"):
        if phrase in lower:
            score += 1
    return score


class NewsFeed:
    def __init__(self, feeds: list[str], max_headlines: int = 60, cache_minutes: int = 10):
        self.feeds = feeds
        self.max_headlines = max_headlines
        self.cache_minutes = cache_minutes
        self._cache: list[str] = []
        self._cache_time = 0.0

    def fetch_headlines(self) -> list[str]:
        if self._cache and time.time() - self._cache_time < self.cache_minutes * 60:
            return self._cache
        headlines = []
        for url in self.feeds:
            try:
                parsed = feedparser.parse(url)
                headlines.extend(e.get("title", "") for e in parsed.entries)
            except Exception as e:
                log.warning("No se pudo leer el feed %s: %s", url, e)
        self._cache = headlines[: self.max_headlines]
        self._cache_time = time.time()
        log.info("Noticias: %d titulares descargados", len(self._cache))
        return self._cache

    def sentiment_for(self, symbol: str) -> float:
        """Sentimiento [-1, 1] de los titulares que mencionan al activo."""
        base = symbol.split("/")[0].upper()
        keywords = ASSET_KEYWORDS.get(base, [base.lower()])
        relevant = [
            h for h in self.fetch_headlines()
            if any(k in h.lower() for k in keywords)
        ]
        if not relevant:
            return 0.0
        total = sum(_score_text(h) for h in relevant)
        # Normaliza: en promedio una nota fuertemente sesgada aporta ~1 punto
        return max(-1.0, min(1.0, total / max(len(relevant), 3)))
