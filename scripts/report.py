"""Reporte de desempeño del paper trading (lee data/state/paper_portfolio.json).

Uso:
    python scripts/report.py           # imprime el reporte
    python scripts/report.py --send    # además lo manda al webhook (ej. Rook)

Tip: programa esto en cron (o pídele a tu agente que lo corra) una vez al día
para recibir el resumen por WhatsApp:
    0 9 * * * cd /home/tradebot/tradebot_alex && venv/bin/python scripts/report.py --send
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config
from bot.execution.paper import STATE_FILE
from bot.notifier import Notifier


def build_report(state: dict) -> str:
    history = state.get("history", [])
    sells = [t for t in history if t["action"] == "SELL"]
    wins = [t for t in sells if (t.get("pnl") or 0) > 0]
    realized = sum(t.get("pnl") or 0 for t in sells)

    lines = ["📊 Reporte tradebot (paper)"]
    lines.append(f"Efectivo: {state.get('cash', 0):,.2f} USD")
    positions = state.get("positions", {})
    if positions:
        lines.append("Posiciones abiertas:")
        for symbol, p in positions.items():
            lines.append(f"  - {symbol}: {p['qty']:.6f} @ {p['entry_price']:,.2f}")
    else:
        lines.append("Sin posiciones abiertas")
    lines.append(f"Operaciones cerradas: {len(sells)}")
    if sells:
        lines.append(f"Aciertos: {len(wins)}/{len(sells)} ({len(wins) / len(sells) * 100:.0f}%)")
        lines.append(f"PnL realizado: {realized:+,.2f} USD")
        last = sells[-1]
        lines.append(f"Última venta: {last['symbol']} pnl {last.get('pnl', 0):+,.2f} USD")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="mandar al webhook configurado")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    state_path = root / STATE_FILE
    if not state_path.exists():
        print("Aún no hay estado de paper trading (corre primero el bot).")
        sys.exit(1)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = build_report(state)
    print(report)

    if args.send:
        config = Config.load(str(root / "config.yaml"))
        if not config.webhook_url:
            print("\nFalta WEBHOOK_URL en el .env, no se envió.")
            sys.exit(1)
        Notifier(webhook_url=config.webhook_url, webhook_token=config.webhook_token,
                 webhook_enabled=True, exchange="paper").notify(report, event="daily_report")
        print("\nReporte enviado al webhook.")


if __name__ == "__main__":
    main()
