# Deployment guide

## VPS deployment

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git

git clone https://github.com/blazenxt/shionmusicbot.git
cd shionmusicbot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
python scripts/generate_session.py
python -m shionmusicbot
```

## systemd service

Create `/etc/systemd/system/shionmusicbot.service`:

```ini
[Unit]
Description=Shion Music bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/shionmusicbot
EnvironmentFile=/opt/shionmusicbot/.env
ExecStart=/opt/shionmusicbot/.venv/bin/python -m shionmusicbot
Restart=always
RestartSec=10
User=shion
Group=shion

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shionmusicbot
sudo journalctl -u shionmusicbot -f
```

## Docker deployment

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f
```

## SFTP-only hosting warning

A Telegram VC music bot needs a long-running Python process and FFmpeg. SFTP/file-manager access alone is not enough unless the host also provides shell/process manager support.
