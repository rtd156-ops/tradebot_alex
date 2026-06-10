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
