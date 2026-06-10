# Migración del VPS a otra región (Hostinger)

El cambio de ubicación en hPanel **reinstala el servidor desde cero**: se
pierde todo el disco (el bot, OpenClaw, credenciales, historial). Este es el
orden correcto para no perder nada.

## 1. ANTES de migrar: respaldo

### 1a. Respaldo de OpenClaw (el agente)

Todo el estado de OpenClaw (config, API keys, tokens, sesión de WhatsApp,
memoria, skills, historial) vive en su directorio de estado, por defecto
`~/.openclaw/` del usuario que lo corre. Hazlo TÚ por SSH (al detener el
gateway, el agente queda fuera de línea y ya no puede responderte):

```bash
openclaw status            # confirma la ruta del state directory
openclaw gateway stop      # detiene el agente para que nada cambie a medio copiado
cd ~ && tar -czf /root/openclaw-state.tgz .openclaw
# si usas perfiles extra (~/.openclaw-<perfil>), archívalos también
```

### 1b. Respaldo del bot de trading

```bash
tar czf /root/respaldo_tradebot.tar.gz \
  /home/tradebot/tradebot_alex/.env \
  /home/tradebot/tradebot_alex/config.local.yaml \
  /home/tradebot/tradebot_alex/data/state/
```

### 1c. Descárgalos FUERA del servidor (desde tu PC)

```powershell
scp root@<ip_actual>:/root/openclaw-state.tgz .
scp root@<ip_actual>:/root/respaldo_tradebot.tar.gz .
```

Los archivos contienen claves en texto plano: guárdalos en un lugar seguro
y bórralos cuando la migración termine. Sin este paso, no continúes.

## 2. Migrar en hPanel

VPS → Cambiar la ubicación del servidor → elige **Lituania** (o
Francia/Alemania) → confirmar. Espera a que termine la reinstalación.
Anota la **nueva IP** (puede cambiar).

## 3. DESPUÉS de migrar: restaurar

### 3a. Restaurar OpenClaw

```bash
# instala Node.js y el CLI de OpenClaw igual que la primera vez, luego:
scp openclaw-state.tgz root@<ip_nueva>:~/     # desde tu PC
cd ~ && tar -xzf openclaw-state.tgz           # en el servidor
openclaw doctor
openclaw gateway restart
openclaw status
```

Con el directorio `.openclaw` restaurado vuelven sus claves, skills,
memoria y la sesión de WhatsApp — el agente despierta siendo él mismo.

### 3b. Restaurar el bot

1. Sube el respaldo: `scp respaldo_tradebot.tar.gz root@<ip_nueva>:/root/`
2. Reinstala el bot siguiendo `deploy/DEPLOY.md` (10 min — puede hacerlo el agente).
3. Restaura encima: `.env`, `config.local.yaml` y `data/state/`
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
