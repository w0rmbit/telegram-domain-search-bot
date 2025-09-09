# Telegram Domain Search Bot

Upload `.txt` files to your Telegram channel and search for domains across them.

## Features
- Auto-index files from channel
- PostgreSQL metadata storage
- Domain search with result file
- Flask health check for Koyeb

## Setup
- Set `BOT_TOKEN`, `DATABASE_URL`, `CHANNEL_ID` in Koyeb env vars
- Deploy with webhook or polling
