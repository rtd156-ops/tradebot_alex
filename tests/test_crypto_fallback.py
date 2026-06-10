import pandas as pd

from bot.data.crypto_feed import CryptoFeed


def test_fallback_to_yahoo_when_bybit_fails(monkeypatch):
    feed = CryptoFeed()

    def bybit_down(*a, **k):
        raise RuntimeError("403 CloudFront")

    fake_df = pd.DataFrame({"timestamp": [], "open": [], "high": [],
                            "low": [], "close": [], "volume": []})
    used = {}

    def fake_yahoo(symbol, timeframe, limit):
        used["symbol"] = symbol
        return fake_df

    monkeypatch.setattr(feed.exchange, "fetch_ohlcv", bybit_down)
    monkeypatch.setattr(feed._fallback, "get_ohlcv", fake_yahoo)

    result = feed.get_ohlcv("BTC/USDT", "1h", 200)
    assert result is fake_df
    assert used["symbol"] == "BTC-USD"
