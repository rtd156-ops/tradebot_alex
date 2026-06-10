"""Manda un evento de prueba al webhook configurado en .env (ej. tu OpenClaw).

Uso:  python scripts/test_webhook.py
Requiere WEBHOOK_URL (y opcionalmente WEBHOOK_TOKEN) en el .env.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config
from bot.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

config = Config.load(str(Path(__file__).resolve().parent.parent / "config.yaml"))
if not config.webhook_url:
    print("Falta WEBHOOK_URL en el .env — agrégala y vuelve a correr este script.")
    sys.exit(1)

notifier = Notifier(webhook_url=config.webhook_url, webhook_token=config.webhook_token,
                    webhook_enabled=True, exchange="paper")
notifier.notify(
    "Prueba de conexión: tradebot_alex -> webhook OK",
    event="trade_closed",
    data={"symbol": "BTCUSDT", "side": "long", "qty": 0.05,
          "entry": 68420, "exit": 69110, "pnl": 34.50, "reason": "test"},
)
print("Evento de prueba enviado. Revisa que tu agente lo haya recibido.")
