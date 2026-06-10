"""Motor del bot: en cada ciclo descarga datos, genera señales y ejecuta órdenes."""
import logging

from .config import Config
from .data.crypto_feed import CryptoFeed
from .data.news_feed import NewsFeed
from .data.stocks_feed import StocksFeed
from .execution.paper import PaperBroker
from .notifier import Notifier
from .risk import RiskManager
from .strategy.strategy import Strategy

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, config: Config):
        self.config = config
        self.crypto = CryptoFeed()
        self.stocks = StocksFeed()
        self.news = NewsFeed(
            feeds=config.news.get("feeds", []),
            max_headlines=config.news.get("max_headlines", 60),
        ) if config.news.get("enabled", True) else None
        self.strategy = Strategy(config.strategy)
        self.risk = RiskManager(config.portfolio)
        self.notifier = Notifier(
            config.telegram_token, config.telegram_chat_id,
            config.notifications.get("telegram", False),
            config.webhook_url, config.webhook_token,
            config.notifications.get("webhook", False),
        )
        self.broker = self._build_broker()

    def _build_broker(self):
        if self.config.mode == "live":
            from .execution.bybit_live import BybitLiveBroker
            log.warning("MODO LIVE: el bot operará con dinero real en Bybit (cripto). "
                        "Las acciones seguirán solo como señales.")
            return BybitLiveBroker(
                self.config.bybit_api_key,
                self.config.bybit_api_secret,
                self.config.bybit_testnet,
            )
        return PaperBroker(
            starting_cash=self.config.paper_starting_cash,
            fee_pct=self.config.portfolio.get("fee_pct", 0.001),
        )

    def _assets(self):
        """(símbolo, feed, ejecutable). En live solo se ejecuta cripto;
        las acciones generan señales informativas."""
        live = self.config.mode == "live"
        for s in self.config.crypto_symbols:
            yield s, self.crypto, True
        for s in self.config.stock_symbols:
            yield s, self.stocks, not live

    def run_cycle(self):
        timeframe = self.config.strategy.get("timeframe", "1h")
        lookback = self.config.strategy.get("lookback_candles", 200)
        prices: dict[str, float] = {}

        context = self.stocks.market_context()
        if context:
            log.info("Contexto de mercado (var. diaria %%): %s", context)

        for symbol, feed, executable in self._assets():
            df = feed.get_ohlcv(symbol, timeframe, lookback)
            if df is None or df.empty:
                continue
            price = float(df["close"].iloc[-1])
            prices[symbol] = price

            # 1. Salidas por riesgo (stop-loss / take-profit) antes que la señal
            pos = self.broker.get_position(symbol) if executable else None
            if pos:
                exit_reason = self.risk.check_exit(pos.entry_price, price)
                if exit_reason and self.broker.sell(symbol, price):
                    self.notifier.notify(f"{exit_reason}: vendido {symbol} @ {price:.2f}")
                    continue

            # 2. Señal de la estrategia (técnicos + noticias)
            sentiment = self.news.sentiment_for(symbol) if self.news else 0.0
            signal = self.strategy.generate(symbol, df, sentiment)

            if not executable:
                if signal.action != "HOLD":
                    self.notifier.notify(
                        f"SEÑAL (sin ejecutar) {signal.action} {symbol} @ {price:.2f} "
                        f"(score {signal.score})")
                continue

            if signal.action == "BUY" and not pos:
                trades_today = getattr(self.broker, "trades_today", lambda: 0)()
                if not self.risk.can_open(trades_today):
                    continue
                value = self.broker.portfolio_value(prices)
                amount = self.risk.position_size(value, self.broker.get_cash())
                if amount >= 10 and self.broker.buy(symbol, amount, price):
                    self.notifier.notify(
                        f"COMPRA {symbol} @ {price:.2f} ({amount:.2f} USD, score {signal.score})")
            elif signal.action == "SELL" and pos:
                if self.broker.sell(symbol, price):
                    self.notifier.notify(
                        f"VENTA {symbol} @ {price:.2f} (score {signal.score})")

        value = self.broker.portfolio_value(prices)
        log.info("Fin de ciclo. Valor del portafolio: %.2f USD (efectivo: %.2f)",
                 value, self.broker.get_cash())
