# Tradebot Alex 🤖📈

Bot de trading que revisa cada cierto tiempo los mercados (criptomonedas en
Bybit, acciones/ETFs e índices vía Yahoo Finance) y las noticias financieras
para generar señales de compra/venta y ejecutarlas automáticamente.

## ¿Cómo funciona?

Cada `interval_minutes` (15 min por defecto) el bot:

1. **Descarga datos** — velas OHLCV de cada activo (Bybit para cripto, Yahoo
   Finance para acciones) y la variación diaria de índices (S&P 500, Nasdaq, VIX).
2. **Lee noticias** — titulares de feeds RSS (CoinDesk, Cointelegraph, Yahoo
   Finance, MarketWatch) y calcula un sentimiento por activo entre -1 y +1.
3. **Genera una señal** — combina indicadores técnicos (cruce de medias SMA
   20/50, RSI 14, MACD) con el sentimiento de noticias en un score ponderado.
   Score ≥ 0.5 → COMPRA, score ≤ -0.5 → VENTA.
4. **Gestiona el riesgo** — máximo 15% del portafolio por posición, stop-loss
   del 5%, take-profit del 10% y máximo 6 compras al día (todo configurable).
5. **Ejecuta** — en modo `paper` simula las órdenes con comisiones; en modo
   `live` opera de verdad en Bybit (las acciones quedan solo como señales).

## Instalación

```bash
python -m venv venv
source venv/bin/activate   # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # llena tus credenciales si vas a usar live/Telegram
```

## Uso

```bash
python main.py --once   # un solo ciclo, ideal para probar
python main.py          # bucle continuo cada interval_minutes
```

El portafolio simulado se guarda en `data/state/paper_portfolio.json` (efectivo,
posiciones e historial de operaciones con PnL), así que sobrevive reinicios.

## Configuración

Todo se ajusta en `config.yaml`: activos, intervalo, parámetros de la
estrategia, límites de riesgo y fuentes de noticias. Las credenciales van
**únicamente** en `.env` (nunca en el YAML ni en el repositorio).

## Pasar a dinero real (cuando la estrategia esté validada)

1. Crea una API key en Bybit con permisos de **solo spot trading** (sin retiros).
2. Ponla en `.env` y deja `BYBIT_TESTNET=true` para probar contra el testnet.
3. Cambia `mode: live` en `config.yaml`.
4. Solo cuando todo funcione en testnet, pon `BYBIT_TESTNET=false`.

> **Nota sobre GBM:** GBM no ofrece API pública de trading, por lo que no es
> posible ejecutar órdenes automáticas ahí. Si más adelante quieres ejecutar
> acciones de verdad, la arquitectura admite agregar un broker con API como
> Alpaca implementando la interfaz `bot/execution/base.py`.

## Modo multi-estrategia

Con `multi_strategy.enabled: true` (default del repo), una sola instancia del
bot corre N estrategias (`conservative`, `normal`, `aggressive`) sobre la
misma wallet, con separación lógica de capital:

- **Ledger SQLite** (`data/state/ledger.sqlite`): fuente de verdad local.
  Cash, posiciones, órdenes, trades, señales (ejecutadas y rechazadas con
  motivo) y eventos, por estrategia. Sobrevive reinicios.
- **Allocator central** (`bot/allocator.py`): cada estrategia solo puede usar
  su `capital_limit_usd`; valida límite diario, posición duplicada, mínimo de
  orden y que el total no exceda el balance real de la wallet.
- **Reconciliación**: en cada ciclo se compara el ledger contra la wallet
  real. Si el ledger reclama más cash/monedas de las que existen, el bot
  **bloquea toda ejecución** y notifica (`balance_check` + `risk_block`).
- **orderLinkId**: cada orden en Bybit viaja etiquetada como
  `<estrategia>-<símbolo>-<timestamp>-<uuid>`, visible en el historial del
  exchange y mapeada localmente en la tabla `orders`.
- **Webhook**: todos los eventos llevan `strategy_id`. Tipos: `signal`,
  `trade_opened`, `trade_closed`, `rejected_signal`, `risk_block`,
  `balance_check`, `heartbeat`, `error`, `daily_report`.

```bash
python main.py --once                          # dry-run de un ciclo (paper)
python scripts/strategy_report.py [--send]     # métricas por estrategia
python scripts/backtest.py --compare           # estrategias sobre los mismos datos
```

### Protecciones (inspiradas en Freqtrade)

Configurables por estrategia en el bloque `portfolio` (heredan del base):

| Parámetro | Qué hace |
|---|---|
| `trailing_stop` + `trailing_stop_positive` + `trailing_stop_positive_offset` | Al superar el offset de ganancia, un stop dinámico sigue al precio pico y asegura ganancias |
| `cooldown_minutes` | Tras cerrar una posición, no recomprar el mismo símbolo durante N minutos |
| `stoploss_guard_limit` / `_lookback_minutes` / `_stop_minutes` | N stop-loss en la ventana pausan las ENTRADAS de la estrategia (las salidas siguen activas) |
| `max_drawdown_pct` + `drawdown_lookback_minutes` | Si el drawdown realizado excede el % del capital en la ventana, se pausan las entradas |

Los rechazos por protección quedan auditados en la tabla `signals`
(`cooldown`, `stoploss_guard`, `max_drawdown`) y se notifican al webhook
solo cuando el motivo cambia (sin spam por ciclo). El backtest simula
trailing stop y cooldown, por lo que `--compare` mide su efecto real.

### Decisiones de arquitectura

- **Bloqueo total ante divergencia**: si ledger y wallet no cuadran, se
  bloquean compras Y ventas (no solo compras). Una divergencia indica
  intervención externa o un bug; operar "a ciegas" podría vender monedas de
  otra estrategia. Se resuelve con intervención humana (ajustar el ledger o
  la wallet) y el bloqueo se libera solo cuando la reconciliación pasa.
- **Cash lógico vs. capital**: el cash de cada estrategia se inicializa con
  su `capital_limit_usd`; si el límite cambia en la config, la diferencia se
  aplica al cash y queda registrada como evento `capital_adjusted`.
- **El rechazo `position_open` no se notifica al webhook** (se repetiría
  cada ciclo mientras la posición siga abierta); sí queda auditado en la
  tabla `signals`.
- **Tolerancia de reconciliación del 2% + 1 USD**: cubre comisiones y
  redondeos de qty del exchange sin enmascarar divergencias reales.
- El modo multi solo opera **cripto**; las acciones siguen disponibles en el
  modo single-strategy (`multi_strategy.enabled: false`), que se conserva
  intacto por compatibilidad.

## Mejora continua (medir la certeza de la estrategia)

El ciclo de iteración del bot tiene tres herramientas:

```bash
python scripts/recommend.py            # ¿qué activos conviene operar hoy?
python scripts/backtest.py             # ¿cómo le habría ido a la estrategia? (--optimize prueba variantes)
python scripts/report.py [--send]      # ¿cómo va el paper trading real? (--send lo manda al webhook)
```

El flujo: backtest para validar cambios de parámetros → ajustar `config.yaml`
→ dejar correr en paper → revisar el reporte (aciertos, PnL realizado) →
repetir. Nunca cambies parámetros solo porque una variante ganó en un
backtest: exige también que tenga sentido y que lo confirme el paper trading
(el backtest no incluye el sentimiento de noticias y puede sobreajustarse al
pasado).

## Pruebas

```bash
pip install pytest
pytest tests/ -v
```

## Estructura

```
main.py                     # punto de entrada (bucle del bot)
config.yaml                 # toda la configuración
bot/
  engine.py                 # orquesta cada ciclo
  config.py                 # carga config + .env
  risk.py                   # stop-loss, take-profit, tamaño de posición
  notifier.py               # alertas por consola y Telegram
  data/
    crypto_feed.py          # velas de Bybit (ccxt)
    stocks_feed.py          # velas e índices de Yahoo Finance
    news_feed.py            # RSS + sentimiento por léxico
  strategy/
    indicators.py           # SMA, RSI, MACD (pandas puro)
    strategy.py             # señal combinada técnica + noticias
  execution/
    base.py                 # interfaz Broker
    paper.py                # broker simulado con estado persistente
    bybit_live.py           # broker real Bybit spot (testnet/mainnet)
```

## Advertencia

Este bot es una herramienta educativa/experimental. Ninguna estrategia
garantiza ganancias; opera bajo tu propio riesgo y nunca inviertas dinero
que no puedas permitirte perder.
