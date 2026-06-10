"""Backtest de la estrategia sobre histórico diario.

Uso:
    python scripts/backtest.py                  # activos cripto del config.yaml
    python scripts/backtest.py --days 365
    python scripts/backtest.py --symbols BTC/USDT ETH/USDT
    python scripts/backtest.py --optimize       # prueba variantes de parámetros
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from bot.backtest import run_backtest
from bot.config import Config
from bot.data.history import fetch_daily

logging.basicConfig(level=logging.WARNING)

# Variantes a explorar con --optimize: (sma_fast, sma_slow, buy_thr, sell_thr)
GRID = [
    (10, 30, 0.5, -0.5),
    (20, 50, 0.5, -0.5),
    (20, 50, 0.4, -0.4),
    (30, 80, 0.5, -0.5),
    (10, 30, 0.4, -0.4),
]


def compare_strategies(config: Config, data: dict, days: int):
    """Corre las estrategias del modo multi sobre los MISMOS datos históricos."""
    strategies = config.strategies()
    if not strategies:
        print("No hay estrategias definidas en multi_strategy.")
        return
    rows = []
    for strat in strategies:
        for symbol, df in data.items():
            if symbol not in strat.assets:
                continue
            r = run_backtest(symbol, df, strat.strategy, strat.portfolio)
            rows.append({
                "estrategia": strat.strategy_id, "símbolo": symbol,
                "operaciones": r.trades, "aciertos_%": round(r.win_rate * 100, 1),
                "retorno_%": r.total_return_pct, "max_dd_%": r.max_drawdown_pct,
                "buy&hold_%": r.buy_hold_pct,
            })
    table = pd.DataFrame(rows)
    print(f"\n=== Backtest comparativo {days} días (mismos datos para todas) ===\n")
    print(table.to_string(index=False))
    print("\n--- Promedio por estrategia ---")
    summary = table.groupby("estrategia")[["retorno_%", "aciertos_%", "operaciones"]].mean().round(1)
    print(summary.to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--compare", action="store_true",
                        help="comparar las estrategias de multi_strategy entre sí")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    config = Config.load(str(root / "config.yaml"))
    symbols = args.symbols or config.crypto_symbols
    if args.compare:
        symbols = args.symbols or sorted(
            {s for strat in config.strategies() for s in strat.assets})

    data = {}
    for symbol in symbols:
        df = fetch_daily(symbol, args.days)
        if df is None or len(df) < 100:
            print(f"(sin datos suficientes para {symbol}, se omite)")
            continue
        data[symbol] = df

    if args.compare:
        compare_strategies(config, data, args.days)
        return

    if not args.optimize:
        rows = []
        for symbol, df in data.items():
            r = run_backtest(symbol, df, config.strategy, config.portfolio)
            rows.append({
                "símbolo": symbol, "operaciones": r.trades,
                "aciertos_%": round(r.win_rate * 100, 1),
                "retorno_%": r.total_return_pct,
                "buy&hold_%": r.buy_hold_pct,
                "max_drawdown_%": r.max_drawdown_pct,
            })
        print(f"\n=== Backtest {args.days} días (parámetros de config.yaml) ===\n")
        print(pd.DataFrame(rows).to_string(index=False))
        print("\nLectura: 'retorno_%' es lo que habría hecho el bot; compáralo "
              "contra 'buy&hold_%' (no hacer nada). 'aciertos_%' con pocas "
              "operaciones no es estadísticamente confiable.")
        return

    print(f"\n=== Optimización ({len(GRID)} variantes x {len(data)} activos) ===\n")
    for symbol, df in data.items():
        results = []
        for fast, slow, buy_thr, sell_thr in GRID:
            params = {**config.strategy, "sma_fast": fast, "sma_slow": slow,
                      "buy_threshold": buy_thr, "sell_threshold": sell_thr}
            r = run_backtest(symbol, df, params, config.portfolio)
            results.append(((fast, slow, buy_thr), r))
        results.sort(key=lambda x: x[1].total_return_pct, reverse=True)
        print(f"--- {symbol} ---")
        for (fast, slow, thr), r in results:
            print(f"  sma {fast:3d}/{slow:3d} umbral ±{thr}: "
                  f"{r.total_return_pct:+7.1f}% en {r.trades:2d} ops "
                  f"(aciertos {r.win_rate * 100:4.1f}%, dd {r.max_drawdown_pct}%)")
        print()


if __name__ == "__main__":
    main()
