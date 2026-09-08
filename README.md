# Discord Audio Bot

Discord-Bot zum automatischen Bearbeiten von Audiodateien.

## Funktionen

- `/master` – einzelne Audiodatei mastern
- `/remix` – zwei Audiodateien zu einem Übergang/Remix verbinden
- Bass-Stufen: wenig, mittel, viel, Bass Boost
- Lautheit: leise, normal, laut, ultra laut
- MP3, WAV, M4A, FLAC, OGG, AAC und OPUS
- Ausgabe als MP3 mit 320 kbit/s

## Installation

```bash
sudo apt update
sudo apt install -y ffmpeg python3 python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Token setzen

Den Bot-Token niemals in GitHub speichern. Setze ihn als Umgebungsvariable:

```bash
export DISCORD_TOKEN="DEIN_NEUER_BOT_TOKEN"
python3 bot.py
```

Falls ein Token bereits öffentlich geteilt wurde, muss er im Discord Developer Portal sofort zurückgesetzt werden.

## Hinweise

Die Verarbeitung nutzt lokale Analyse und FFmpeg. Es wird keine externe KI-API benötigt. Für echte Stem-Separation oder vollständig professionelle DJ-Remixe wäre zusätzlich ein lokales Audio-Separationsmodell erforderlich.
