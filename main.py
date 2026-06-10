"""Punto de entrada del bot de trading.

Uso:
    python main.py            # corre en bucle cada interval_minutes
    python main.py --once     # ejecuta un solo ciclo (útil para probar o cron)
"""
import argparse
import logging
import sys
import time

from bot.config import Config
from bot.engine import Engine


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    parser = argparse.ArgumentParser(description="Bot de trading (Bybit + acciones)")
    parser.add_argument("--once", action="store_true", help="Ejecuta un solo ciclo y termina")
    parser.add_argument("--config", default="config.yaml", help="Ruta del archivo de configuración")
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger("main")

    config = Config.load(args.config)
    log.info("Modo: %s | Intervalo: %d min | Cripto: %s | Acciones: %s",
             config.mode.upper(), config.interval_minutes,
             config.crypto_symbols, config.stock_symbols)

    if config.mode == "live" and not config.bybit_testnet:
        log.warning("¡ATENCIÓN! Modo LIVE con dinero real. Tienes 10 segundos para cancelar (Ctrl+C)...")
        time.sleep(10)

    if config.multi_strategy_enabled:
        from bot.multi_engine import MultiEngine
        log.info("Modo MULTI-ESTRATEGIA: %s",
                 [s.strategy_id for s in config.strategies()])
        engine = MultiEngine(config)
    else:
        engine = Engine(config)

    while True:
        try:
            engine.run_cycle()
        except KeyboardInterrupt:
            log.info("Bot detenido por el usuario")
            break
        except Exception:
            log.exception("Error en el ciclo; se reintentará en el siguiente intervalo")
        if args.once:
            break
        time.sleep(config.interval_minutes * 60)


if __name__ == "__main__":
    main()
