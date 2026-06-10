"""Backtesting: simula la estrategia del bot sobre velas históricas.

Reproduce las mismas reglas del motor en vivo (señal BUY/SELL, stop-loss y
take-profit intra-vela, comisiones) y devuelve métricas para evaluar la
certeza de la estrategia: número de operaciones, % de aciertos, retorno
total, drawdown máximo y comparación contra comprar-y-mantener.

Nota: el backtest no incluye sentimiento de noticias (no hay titulares
históricos), por lo que mide solo la parte técnica de la estrategia.
"""
from dataclasses import dataclass, field

import pandas as pd

from .risk import RiskManager
from .strategy.models import build_strategy


@dataclass
class BacktestResult:
    symbol: str
    trades: int = 0
    wins: int = 0
    total_return_pct: float = 0.0
    buy_hold_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_log: list = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0


def run_backtest(symbol: str, df: pd.DataFrame, strategy_params: dict,
                 risk_params: dict, fee_pct: float = 0.001) -> BacktestResult:
    strategy = build_strategy(strategy_params)
    risk = RiskManager(risk_params)
    result = BacktestResult(symbol=symbol)

    warmup = strategy.min_candles
    if len(df) <= warmup + 1:
        return result

    close = df["close"].reset_index(drop=True)
    low = df["low"].reset_index(drop=True)
    high = df["high"].reset_index(drop=True)

    equity = 1.0          # multiplicador de capital realizado
    curve = []            # equity valuada a mercado, para el drawdown
    in_pos = False
    entry = 0.0
    peak = 0.0
    last_exit_i = None
    # Cooldown en velas: minutos / duración estimada de la vela (diaria)
    cooldown_candles = int(risk_params.get("cooldown_minutes", 0) / 1440 + 0.999)

    for i in range(warmup, len(df)):
        price = float(close[i])

        if in_pos:
            sl_price = entry * (1 - risk.stop_loss_pct)
            tp_price = entry * (1 + risk.take_profit_pct)
            exit_price = reason = None
            # El stop se evalúa primero: dentro de la vela, el peor caso manda
            if float(low[i]) <= sl_price:
                exit_price, reason = sl_price, "stop_loss"
            elif (risk.trailing_stop and peak >= entry * (1 + risk.trailing_offset)
                  and float(low[i]) <= peak * (1 - risk.trailing_pct)):
                exit_price, reason = peak * (1 - risk.trailing_pct), "trailing_stop"
            elif float(high[i]) >= tp_price:
                exit_price, reason = tp_price, "take_profit"
            else:
                signal = strategy.generate(symbol, df.iloc[: i + 1], 0.0)
                if signal.action == "SELL":
                    exit_price, reason = price, "signal"
            # El pico se actualiza tras evaluar la vela (conservador: el máximo
            # de esta vela no puede disparar su propio trailing)
            peak = max(peak, float(high[i]))
            if exit_price is not None:
                trade_ret = exit_price / entry * (1 - fee_pct) ** 2 - 1
                equity *= 1 + trade_ret
                result.trades += 1
                result.wins += trade_ret > 0
                result.trade_log.append({
                    "exit_time": str(df["timestamp"].iloc[i]), "entry": round(entry, 4),
                    "exit": round(exit_price, 4), "ret_pct": round(trade_ret * 100, 2),
                    "reason": reason,
                })
                in_pos = False
                last_exit_i = i
        else:
            if (cooldown_candles and last_exit_i is not None
                    and i - last_exit_i < cooldown_candles):
                curve.append(equity)
                continue
            signal = strategy.generate(symbol, df.iloc[: i + 1], 0.0)
            if signal.action == "BUY":
                in_pos = True
                entry = price
                peak = price

        curve.append(equity * (price / entry) if in_pos else equity)

    # Cierra la posición abierta al final, a precio de la última vela
    if in_pos:
        trade_ret = float(close.iloc[-1]) / entry * (1 - fee_pct) ** 2 - 1
        equity *= 1 + trade_ret
        result.trades += 1
        result.wins += trade_ret > 0
        result.trade_log.append({
            "exit_time": str(df["timestamp"].iloc[-1]), "entry": round(entry, 4),
            "exit": round(float(close.iloc[-1]), 4),
            "ret_pct": round(trade_ret * 100, 2), "reason": "fin_de_datos",
        })

    series = pd.Series(curve)
    drawdown = (series / series.cummax() - 1).min() if len(series) else 0.0
    result.max_drawdown_pct = round(float(drawdown) * 100, 1)
    result.total_return_pct = round((equity - 1) * 100, 1)
    result.buy_hold_pct = round((float(close.iloc[-1]) / float(close[warmup]) - 1) * 100, 1)
    return result
