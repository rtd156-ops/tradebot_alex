"""Reporte comparativo por estrategia (lee el ledger SQLite del modo multi).

Uso:
    python scripts/strategy_report.py            # tabla comparativa
    python scripts/strategy_report.py --send     # además la manda al webhook
    python scripts/strategy_report.py --no-prices  # sin precios en vivo (offline)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from bot.config import Config
from bot.ledger import DEFAULT_PATH, Ledger
from bot.notifier import Notifier


def metrics_for(ledger: Ledger, sid: str, prices: dict[str, float]) -> dict:
    trades = ledger.trades(sid)
    wins = [t for t in trades if t["pnl"] > 0]
    positions = ledger.positions(sid)
    cash = ledger.cash(sid)

    exposure = sum(p["cost"] for p in positions)
    unrealized = sum(
        p["qty"] * prices.get(p["symbol"], p["entry_price"]) - p["cost"]
        for p in positions)
    realized = sum(t["pnl"] for t in trades)

    # Drawdown aproximado sobre la curva de PnL realizado acumulado
    curve = pd.Series([t["pnl"] for t in trades]).cumsum()
    capital = ledger.capital_limit(sid) or 1
    drawdown = float(((curve - curve.cummax()) / capital).min() * 100) if len(curve) else 0.0

    signals = ledger.signal_counts(sid)
    rejects = ledger.reject_counts(sid)
    return {
        "estrategia": sid,
        "capital": round(capital, 2),
        "cash": round(cash, 2),
        "exposición": round(exposure, 2),
        "pnl_realizado": round(realized, 2),
        "pnl_no_realizado": round(unrealized, 2),
        "trades": len(trades),
        "aciertos_%": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "max_dd_%": round(drawdown, 1),
        "mejor": round(max((t["pnl"] for t in trades), default=0.0), 2),
        "peor": round(min((t["pnl"] for t in trades), default=0.0), 2),
        "BUY/SELL/HOLD": f"{signals.get('BUY', 0)}/{signals.get('SELL', 0)}/{signals.get('HOLD', 0)}",
        "rechazadas": sum(rejects.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--no-prices", action="store_true",
                        help="no consultar precios en vivo (PnL no realizado al costo)")
    parser.add_argument("--db", default=None, help="ruta del ledger sqlite")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    db_path = args.db or str(root / DEFAULT_PATH)
    if not Path(db_path).exists():
        print(f"No existe el ledger ({db_path}). Corre primero el bot en modo multi.")
        sys.exit(1)

    config = Config.load(str(root / "config.yaml"))
    ledger = Ledger(db_path)

    prices: dict[str, float] = {}
    if not args.no_prices:
        from bot.data.crypto_feed import CryptoFeed
        feed = CryptoFeed()
        symbols = {p["symbol"] for s in config.strategies()
                   for p in ledger.positions(s.strategy_id)}
        for symbol in symbols:
            price = feed.get_price(symbol)
            if price:
                prices[symbol] = price

    rows = [metrics_for(ledger, s.strategy_id, prices) for s in config.strategies()]
    if not rows:
        print("No hay estrategias habilitadas en la config.")
        sys.exit(1)
    table = pd.DataFrame(rows)
    print("\n=== Reporte por estrategia ===\n")
    print(table.to_string(index=False))

    rejects_detail = {s.strategy_id: ledger.reject_counts(s.strategy_id)
                      for s in config.strategies()}
    print("\nSeñales rechazadas por motivo:")
    for sid, detail in rejects_detail.items():
        print(f"  {sid}: {detail or 'ninguna'}")

    if args.send:
        if not config.webhook_url:
            print("\nFalta WEBHOOK_URL en el .env, no se envió.")
            sys.exit(1)
        text = "📊 Reporte por estrategia\n" + "\n".join(
            f"[{r['estrategia']}] PnL {r['pnl_realizado']:+.2f} USD realizado / "
            f"{r['pnl_no_realizado']:+.2f} abierto | {r['trades']} trades "
            f"({r['aciertos_%']}% aciertos) | cash {r['cash']:.2f}"
            for r in rows)
        Notifier(webhook_url=config.webhook_url, webhook_token=config.webhook_token,
                 webhook_enabled=True,
                 exchange="bybit" if config.mode == "live" else "paper",
                 ).notify(text, event="daily_report",
                          data={"strategies": {r["estrategia"]: r for r in rows}})
        print("\nReporte enviado al webhook.")


if __name__ == "__main__":
    main()
