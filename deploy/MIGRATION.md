# Migración del VPS a otra región (Hostinger)

El cambio de ubicación en hPanel **reinstala el servidor desde cero**: se
pierde todo el disco (el bot, OpenClaw, credenciales, historial). Este es el
orden correcto para no perder nada.

## 1. ANTES de migrar: respaldo (lo hace el agente o tú por SSH)

Empaqueta lo irreemplazable:

```bash
tar czf /root/respaldo_tradebot.tar.gz \
  /home/tradebot/tradebot_alex/.env \
  /home/tradebot/tradebot_alex/config.local.yaml \
  /home/tradebot/tradebot_alex/data/state/
# + lo que el agente (OpenClaw) necesite respaldar de sí mismo:
#   su configuración, secretos y datos (su propia carpeta/.env)
```

Descárgalo FUERA del servidor (desde tu PC):

```powershell
scp root@<ip_actual>:/root/respaldo_tradebot.tar.gz .
```

Sin este paso, no continúes.

## 2. Migrar en hPanel

VPS → Cambiar la ubicación del servidor → elige **Lituania** (o
Francia/Alemania) → confirmar. Espera a que termine la reinstalación.
Anota la **nueva IP** (puede cambiar).

## 3. DESPUÉS de migrar: restaurar

1. Reinstala OpenClaw (el agente) igual que la primera vez y restaura su respaldo.
2. Sube el respaldo del bot: `scp respaldo_tradebot.tar.gz root@<ip_nueva>:/root/`
3. Reinstala el bot siguiendo `deploy/DEPLOY.md` (10 min).
4. Restaura encima: `.env`, `config.local.yaml` y `data/state/`
   (propietario `tradebot`, y `chmod 600 .env`).

## 4. Validar que la nueva región sí llega a Bybit

```bash
curl -s https://api.bybit.com/v5/market/time
curl -s https://api-testnet.bybit.com/v5/market/time
```

Ambos deben responder JSON (`"retCode":0`), no un error de CloudFront.
En el log del bot ya no deberían aparecer los warnings "usando Yahoo Finance".

## 5. Dejarlo listo para live (testnet)

En `config.local.yaml`:

```yaml
mode: live
notifications:
  webhook: true
```

En el `.env`: keys de **testnet** y `BYBIT_TESTNET=true`. Reinicia
(`systemctl restart tradebot`) y verifica en el log: `Bybit en modo TESTNET`.

## 6. Seguridad post-migración

- Edita la API key en testnet.bybit.com y restríngela a la **nueva IP** del VPS.
- Firewall: `ufw allow ssh && ufw enable`.
- El paso a dinero real (`BYBIT_TESTNET=false` + keys de mainnet creadas con
  solo Spot Trade e IP restringida) se hace únicamente cuando la estrategia
  haya demostrado resultados en testnet.
