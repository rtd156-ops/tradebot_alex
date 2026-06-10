"""Notificaciones de operaciones: consola siempre; Telegram y webhook opcionales.

El webhook permite conectar agentes externos (por ejemplo OpenClaw): el bot
hace POST con JSON {"text": mensaje} a WEBHOOK_URL, con el token de
WEBHOOK_TOKEN como Bearer en el header Authorization si está definido.
"""
import logging

import requests

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, telegram_token: str = "", telegram_chat_id: str = "",
                 telegram_enabled: bool = False,
                 webhook_url: str = "", webhook_token: str = "",
                 webhook_enabled: bool = False):
        self.telegram_enabled = telegram_enabled and telegram_token and telegram_chat_id
        self.token = telegram_token
        self.chat_id = telegram_chat_id
        self.webhook_enabled = webhook_enabled and webhook_url
        self.webhook_url = webhook_url
        self.webhook_token = webhook_token

    def notify(self, message: str):
        log.info("NOTIFICACIÓN: %s", message)
        if self.telegram_enabled:
            self._send_telegram(message)
        if self.webhook_enabled:
            self._send_webhook(message)

    def _send_telegram(self, message: str):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message},
                timeout=10,
            )
        except requests.RequestException as e:
            log.warning("No se pudo enviar el mensaje de Telegram: %s", e)

    def _send_webhook(self, message: str):
        headers = {"Content-Type": "application/json"}
        if self.webhook_token:
            headers["Authorization"] = f"Bearer {self.webhook_token}"
        try:
            resp = requests.post(
                self.webhook_url, json={"text": message},
                headers=headers, timeout=10,
            )
            if resp.status_code >= 400:
                log.warning("Webhook respondió %d: %s", resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            log.warning("No se pudo enviar al webhook: %s", e)
