"""Notificaciones de operaciones: consola siempre; Telegram y webhook opcionales.

El webhook está pensado para agentes externos (por ejemplo OpenClaw): el bot
hace POST a WEBHOOK_URL con un JSON estructurado por evento:

    {
      "event": "trade_opened" | "trade_closed" | "signal",
      "timestamp": "2026-06-10T18:00:00+00:00",
      "exchange": "paper" | "bybit",
      "strategy": "sma-rsi-macd-news",
      "text": "mensaje legible",
      ... campos del evento: symbol, side, qty, price, entry, exit, pnl, ...
    }

Si WEBHOOK_TOKEN está definido se envía en los headers "X-Webhook-Secret"
y "Authorization: Bearer <token>" para que el receptor valide el origen.
"""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

STRATEGY_NAME = "sma-rsi-macd-news"


class Notifier:
    def __init__(self, telegram_token: str = "", telegram_chat_id: str = "",
                 telegram_enabled: bool = False,
                 webhook_url: str = "", webhook_token: str = "",
                 webhook_enabled: bool = False, exchange: str = "paper"):
        self.telegram_enabled = telegram_enabled and telegram_token and telegram_chat_id
        self.token = telegram_token
        self.chat_id = telegram_chat_id
        self.webhook_enabled = webhook_enabled and webhook_url
        self.webhook_url = webhook_url
        self.webhook_token = webhook_token
        self.exchange = exchange

    def notify(self, message: str, event: str = "info", data: dict | None = None):
        log.info("NOTIFICACIÓN: %s", message)
        if self.telegram_enabled:
            self._send_telegram(message)
        if self.webhook_enabled:
            payload = {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "exchange": self.exchange,
                "strategy": STRATEGY_NAME,
                "text": message,
                **(data or {}),
            }
            self._send_webhook(payload)

    def _send_telegram(self, message: str):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message},
                timeout=10,
            )
        except requests.RequestException as e:
            log.warning("No se pudo enviar el mensaje de Telegram: %s", e)

    def _send_webhook(self, payload: dict):
        headers = {"Content-Type": "application/json"}
        if self.webhook_token:
            headers["X-Webhook-Secret"] = self.webhook_token
            headers["Authorization"] = f"Bearer {self.webhook_token}"
        try:
            resp = requests.post(self.webhook_url, json=payload, headers=headers, timeout=10)
            if resp.status_code >= 400:
                log.warning("Webhook respondió %d: %s", resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            log.warning("No se pudo enviar al webhook: %s", e)
