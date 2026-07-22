# Surprise Prayer Bot

A Telegram bot that pairs people up to pray for each other anonymously.

## Commands

- `/start` — join the prayer pool
- `/myperson` — get assigned someone to pray for
- `/send <message>` — send an anonymous message to your person
- `/leave` — leave the pool
- `/help` — show this

## Deploy

```bash
cp .env.example .env
# edit .env with your TELEGRAM_BOT_TOKEN
docker compose up -d --build
```