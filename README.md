---
title: WizeTravel
emoji: ✈️
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.32.0
app_file: app.py
pinned: false
license: mit
short_description: AI-powered travel planner — flights, hotels, deals, alerts
---

# WizeTravel

AI-powered travel planning suite. Part of [WizeLife](https://wizelife.ai).

**Features:**
- ✈️ Flight search (Amadeus + Kiwi)
- 🏨 Hotel offers
- 🎯 Active deal hunting (RSS, Reddit, news)
- 🤖 AI trip planner (Gemini)
- 📊 Personal price DNA + AI predictions
- 🔔 Multi-channel alerts (Telegram, WhatsApp, ntfy, email)
- 🗺️ Hidden-city, stopover & positioning flight finder
- 💱 Real-time FX rates
- 📋 Visa checker
- 📅 Weekly digest

**Stack:** Streamlit + FastAPI + Google Gemini + Amadeus + SQLite

## Required environment variables (Space Secrets)

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | AI features (planner, predictor, parser) |
| `AMADEUS_CLIENT_ID` | yes | Flight & hotel search |
| `AMADEUS_CLIENT_SECRET` | yes | (paired with above) |
| `KIWI_API_KEY` | optional | Alternate flight search |
| `TELEGRAM_BOT_TOKEN` | optional | Telegram alerts |
| `TELEGRAM_CHAT_ID` | optional | (paired with above) |
| `TWILIO_ACCOUNT_SID` | optional | WhatsApp alerts |
| `TWILIO_AUTH_TOKEN` | optional | (paired with above) |
| `TWILIO_WHATSAPP_FROM` | optional | (paired with above) |
| `NTFY_TOPIC` | optional | Push notifications |
| `NTFY_SERVER` | optional | (defaults to ntfy.sh) |
