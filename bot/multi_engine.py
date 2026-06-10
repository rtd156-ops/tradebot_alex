"""Motor multi-estrategia: N estrategias en una sola instancia, una wallet.

Flujo de cada ciclo:
  1. Descarga datos de mercado y noticias UNA vez (compartidos).
  2. Reconcilia el ledger lógico contra la wallet real; si no cuadran,
     bloquea toda ejecución y notifica (evento balance_check + risk_block).
  3. Por cada estrategia habilitada y cada activo permitido:
     salidas por riesgo -> señal -> validación del allocator -> ejecución.
  4. Toda señal (ejecutada o rechazada, con motivo) queda en el ledger y
     los eventos relevantes van al webhook con su strategy_id.

Solo opera pares de cripto (BASE/QUOTE); las acciones siguen disponibles en
el modo single-strategy.
"""
import logging

from .allocator import Allocator
from .config import Config
from .data.crypto_feed import CryptoFeed
from .data.news_feed import NewsFeed
from .execution.clients import BybitExecution, PaperExecution, make_order_link_id
from .ledger import Ledger
from .notifier import Notifier
from .risk import RiskManager
from .strategy.strategy import Strategy

log = logging.getLogger(__name__)


class MultiEngine:
    def __init__(self, config: Config, ledger: Ledger | None = None,
                 execution=None):
        self.config = config
        self.fee_pct = config.portfolio.get("fee_pct", 0.001)
        self.strategies = config.strategies()
        if not self.strategies:
            raise ValueError("multi_strategy.enabled=true pero no hay estrategias habilitadas")

        self.ledger = ledger or Ledger()
        self.allocator = Allocator(self.ledger)
        self.execution = execution or self._build_execution()
        self.feed = CryptoFeed()
        self.news = NewsFeed(
            feeds=config.news.get("feeds", []),
            max_headlines=config.news.get("max_headlines", 60),
        ) if config.news.get("enabled", True) else None
        self.notifier = Notifier(
            config.telegram_token, config.telegram_chat_id,
            config.notifications.get("telegram", False),
            config.webhook_url, config.webhook_token,
            config.notifications.get("webhook", False),
            exchange="bybit" if config.mode == "live" else "paper",
        )
        self._last_heartbeat = 0.0

        # Instancias por estrategia (señal + riesgo) y registro en el ledger
        self._engines = {}
        for s in self.strategies:
            self.ledger.ensure_strategy(s.strategy_id, s.capital_limit_usd)
            self._engines[s.strategy_id] = (Strategy(s.strategy), RiskManager(s.portfolio))
            log.info("Estrategia '%s': capital %.2f USD, activos %s",
                     s.strategy_id, s.capital_limit_usd, s.assets)

    def _build_execution(self):
        if self.config.mode == "live":
            log.warning("MODO LIVE multi-estrategia (testnet=%s)", self.config.bybit_testnet)
            return BybitExecution(self.config.bybit_api_key, self.config.bybit_api_secret,
                                  self.config.bybit_testnet, self.fee_pct)
        return PaperExecution(self.config.paper_starting_cash, self.fee_pct)

    # --- Ciclo principal ---
    def run_cycle(self):
        timeframe = self.config.strategy.get("timeframe", "1h")
        lookback = self.config.strategy.get("lookback_candles", 200)

        symbols = sorted({sym for s in self.strategies for sym in s.assets if "/" in sym})
        market = {}
        for symbol in symbols:
            df = self.feed.get_ohlcv(symbol, timeframe, lookback)
            if df is not None and not df.empty:
                market[symbol] = df
        sentiment = {s: (self.news.sentiment_for(s) if self.news else 0.0) for s in market}

        balances = self.execution.fetch_balances()
        problems = self.allocator.reconcile(balances)
        if problems:
            self.notifier.notify(
                f"⛔ Ledger y wallet no cuadran, ejecución bloqueada: {'; '.join(problems)}",
                event="balance_check",
                data={"status": "mismatch", "problems": problems})
        usdt_available = float(balances.get("USDT", 0))

        for strat in self.strategies:
            usdt_available = self._run_strategy(strat, market, sentiment, usdt_available)

        self._heartbeat(balances, len(market))

    def _run_strategy(self, strat, market: dict, sentiment: dict,
                      usdt_available: float) -> float:
        sid = strat.strategy_id
        strategy, risk = self._engines[sid]

        for symbol in strat.assets:
            df = market.get(symbol)
            if df is None:
                continue
            price = float(df["close"].iloc[-1])

            # 1. Salidas por riesgo de la posición lógica de ESTA estrategia
            pos = self.ledger.position(sid, symbol)
            if pos:
                exit_reason = risk.check_exit(pos["entry_price"], price)
                if exit_reason:
                    self._close(strat, symbol, pos, price, exit_reason.lower())
                    continue

            # 2. Señal con los parámetros propios de la estrategia
            signal = strategy.generate(symbol, df, sentiment.get(symbol, 0.0))

            if signal.action == "BUY" and pos:
                # Rechazo esperado y repetitivo: se audita pero no se notifica
                self._reject(sid, signal, "position_open", notify=False)
            elif signal.action == "BUY":
                amount = self.allocator.position_size(strat)
                ok, reason = self.allocator.check_buy(
                    strat, symbol, amount, self.fee_pct, usdt_available)
                if not ok:
                    self._reject(sid, signal, reason)
                    continue
                link_id = make_order_link_id(sid, symbol)
                fill = self.execution.market_buy(symbol, amount, price, link_id)
                if fill is None:
                    self._reject(sid, signal, "execution_error")
                    continue
                self.ledger.open_position(sid, symbol, fill.qty, fill.price,
                                          fill.cost, link_id)
                self.ledger.record_signal(sid, symbol, "BUY", signal.score, price, True)
                usdt_available -= fill.cost
                self.notifier.notify(
                    f"[{sid}] COMPRA {symbol} @ {fill.price:.2f} "
                    f"({amount:.2f} USD, score {signal.score})",
                    event="trade_opened",
                    data={"strategy_id": sid, "symbol": symbol.replace("/", ""),
                          "side": "long", "qty": round(fill.qty, 8),
                          "price": fill.price, "usd_amount": round(amount, 2),
                          "score": signal.score, "order_link_id": link_id})
            elif signal.action == "SELL" and pos:
                ok, reason = self.allocator.check_sell(strat, symbol)
                if not ok:
                    self._reject(sid, signal, reason)
                    continue
                self._close(strat, symbol, pos, price, "signal", signal.score)
            else:
                self.ledger.record_signal(sid, symbol, signal.action,
                                          signal.score, price, False)
        return usdt_available

    def _close(self, strat, symbol: str, pos: dict, price: float,
               reason: str, score: float | None = None):
        sid = strat.strategy_id
        ok, why = self.allocator.check_sell(strat, symbol)
        if not ok:
            self.ledger.record_signal(sid, symbol, "SELL", score or 0.0, price, False, why)
            return
        link_id = make_order_link_id(sid, symbol)
        fill = self.execution.market_sell(symbol, pos["qty"], price, link_id)
        if fill is None:
            self.ledger.record_event("error", sid, f"venta fallida {symbol} ({link_id})")
            self.notifier.notify(f"[{sid}] ERROR al vender {symbol}", event="error",
                                 data={"strategy_id": sid, "symbol": symbol.replace("/", "")})
            return
        pnl = self.ledger.close_position(sid, symbol, fill.price, fill.cost,
                                         reason, link_id)
        self.ledger.record_signal(sid, symbol, "SELL", score or 0.0, price, True)
        self.notifier.notify(
            f"[{sid}] VENTA {symbol} @ {fill.price:.2f} ({reason}, PnL {pnl:+.2f} USD)",
            event="trade_closed",
            data={"strategy_id": sid, "symbol": symbol.replace("/", ""), "side": "long",
                  "qty": round(pos["qty"], 8), "entry": pos["entry_price"],
                  "exit": fill.price, "pnl": round(pnl, 2), "reason": reason,
                  "order_link_id": link_id, **({"score": score} if score is not None else {})})

    def _reject(self, sid: str, signal, reason: str, notify: bool = True):
        self.ledger.record_signal(sid, signal.symbol, signal.action,
                                  signal.score, signal.price, False, reason)
        log.info("[%s] señal %s %s rechazada: %s", sid, signal.action,
                 signal.symbol, reason)
        if not notify:
            return
        self.notifier.notify(
            f"[{sid}] Señal {signal.action} {signal.symbol} rechazada: {reason}",
            event="rejected_signal",
            data={"strategy_id": sid, "symbol": signal.symbol.replace("/", ""),
                  "action": signal.action, "score": signal.score, "reason": reason})

    def _heartbeat(self, balances: dict, assets_ok: int):
        import time
        hours = self.config.notifications.get("heartbeat_hours", 0)
        if not hours or time.time() - self._last_heartbeat < hours * 3600:
            return
        self._last_heartbeat = time.time()
        per_strategy = {s.strategy_id: round(self.ledger.cash(s.strategy_id), 2)
                        for s in self.strategies}
        self.notifier.notify(
            f"💓 Bot multi-estrategia activo ({self.config.mode}). "
            f"Cash por estrategia: {per_strategy}. Activos con datos: {assets_ok}.",
            event="heartbeat",
            data={"mode": self.config.mode, "strategies_cash": per_strategy,
                  "usdt_wallet": round(float(balances.get('USDT', 0)), 2),
                  "assets_ok": assets_ok})
