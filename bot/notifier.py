"""Notificaciones de operaciones: consola siempre, Telegram opcional."""
import logging

import requests

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, telegram_token: str = "", telegram_chat_id: str = "", telegram_enabled: bool = False):
        self.telegram_enabled = telegram_enabled and telegram_token and telegram_chat_id
        self.token = telegram_token
        self.chat_id = telegram_chat_id

    def notify(self, message: str):
        log.info("NOTIFICACIÓN: %s", message)
        if self.telegram_enabled:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": message},
                    timeout=10,
                )
            except requests.RequestException as e:
                log.warning("No se pudo enviar el mensaje de Telegram: %s", e)
