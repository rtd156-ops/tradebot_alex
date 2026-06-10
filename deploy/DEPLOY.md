# Desplegar el bot en un VPS (Ubuntu/Debian)

Guía para dejar el bot corriendo 24/7 con reinicio automático si se cae
o si el servidor se reinicia.

## 1. Preparar el servidor (una sola vez)

Conéctate por SSH y crea un usuario dedicado (no uses root para el bot):

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
sudo adduser --disabled-password --gecos "" tradebot
```

## 2. Instalar el bot

```bash
sudo -u tradebot -i
git clone https://github.com/rtd156-ops/tradebot_alex.git
cd tradebot_alex
git checkout claude/awesome-galileo-rgtta1
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env        # pega tus credenciales (Bybit testnet, webhook de OpenClaw)
nano config.yaml # revisa mode, activos y notificaciones
exit
```

Prueba un ciclo antes de dejarlo fijo:

```bash
sudo -u tradebot -i bash -c "cd tradebot_alex && venv/bin/python main.py --once"
```

## 3. Dejarlo corriendo 24/7 (systemd)

```bash
sudo cp /home/tradebot/tradebot_alex/deploy/tradebot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradebot
```

Comandos útiles:

```bash
systemctl status tradebot              # ¿está corriendo?
journalctl -u tradebot -f              # ver el log en vivo
journalctl -u tradebot --since today   # log del día
sudo systemctl restart tradebot        # reiniciar (ej. tras cambiar config)
sudo systemctl stop tradebot           # detener
```

## 3.1 Configuración propia del servidor (config.local.yaml)

No edites `config.yaml` en el servidor: un `git pull` puede pisarlo. Crea un
`config.local.yaml` junto a él (está en `.gitignore`) solo con lo que cambie
en esta máquina, por ejemplo:

```yaml
mode: paper
notifications:
  webhook: true
```

Sus valores se aplican encima de `config.yaml` al arrancar el bot.

## 3.2 Migrar del bot single-strategy al multi-estrategia

El modo multi viene activado en `config.yaml` del repo. Para actualizar un
servidor que ya corre el bot, sin perder configuración local:

```bash
sudo -u tradebot -i bash -c "cd tradebot_alex && git pull origin claude/awesome-galileo-rgtta1"
sudo systemctl restart tradebot
```

- Tu `config.local.yaml` y `.env` no se tocan (mode, webhook y keys siguen
  igual). Para volver al modo clásico: `multi_strategy: {enabled: false}`
  en `config.local.yaml`.
- El primer arranque crea `data/state/ledger.sqlite` con el cash inicial de
  cada estrategia. El estado del modo single (`paper_portfolio.json`) no se
  migra: las posiciones lógicas multi empiezan en cero.
- En testnet, verifica que la wallet tenga al menos la suma de los
  `capital_limit_usd` (10,000 USDT con la config default); si no, la
  reconciliación bloqueará la ejecución por diseño.
- Verifica en el log: `Modo MULTI-ESTRATEGIA: ['conservative', 'normal',
  'aggressive']` y el heartbeat con el cash por estrategia.

## 4. Actualizar el bot cuando haya cambios

```bash
sudo -u tradebot -i bash -c "cd tradebot_alex && git pull origin claude/awesome-galileo-rgtta1 && venv/bin/pip install -r requirements.txt"
sudo systemctl restart tradebot
```

## 5. Seguridad recomendada

- **Restringe la API key de Bybit a la IP del VPS**: en Bybit edita la key,
  elige "Only IPs with permissions granted..." y pon la IP pública del
  servidor (la ves con `curl ifconfig.me`). Así, aunque alguien robe la key,
  no podrá usarla desde otra máquina, y además la key ya no expira a los 3 meses.
- La key debe seguir siendo **solo Read-Write + SPOT Trade, sin retiros**.
- Firewall básico: `sudo ufw allow ssh && sudo ufw enable` (el bot no abre
  puertos, solo hace llamadas salientes).
- Mantén el sistema al día: `sudo apt update && sudo apt upgrade` de vez en cuando.
- El `.env` vive solo en el VPS con permisos del usuario tradebot:
  `chmod 600 /home/tradebot/tradebot_alex/.env`.

## Nota si OpenClaw corre en el mismo VPS

Si tu agente (Rook) está en este mismo servidor, en el `.env` puedes usar
`WEBHOOK_URL=http://127.0.0.1:<puerto>/webhooks/trading` y el tráfico nunca
sale de la máquina.
