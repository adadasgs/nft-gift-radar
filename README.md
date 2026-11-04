# NFT Gift Radar

Telegram bot for monitoring Telegram NFT gift listings and publishing them into group forum topics.

## Implemented foundation
- `/start` explains how to connect the bot.
- `/setup` creates five forum topics in a supergroup: up to 5 TON, 5–15 TON, 15–27.5 TON, 27.5–60 TON, and 60+ TON.
- `/status` shows connected group count.
- SQLite persistence for chats, lots, and reservations.
- Atomic reservation: only one user can reserve a lot; reservation stays until that user releases it.
- Personal reservation log and release button.
- Marketplace adapter interface and a Portals API reader.

## Important: source and currency limitations
The Portals Partners API search returns listing prices in **GRAM**, not TON. Its documented market config returns GRAM ruble/USD rates and a TON/USDT-related market setting, but it does not document a GRAM-to-TON conversion. This project therefore deliberately refuses to label GRAM prices as TON or put them into TON price categories. Portals listings are not yet published until a verified conversion is implemented or the source provides TON-denominated prices.

Other marketplaces (Fragment, Tonnel, Getgems, etc.) are not yet active integrations. The adapter interface is ready, but each source needs a verified public or authorized data interface. The bot must not claim to monitor a marketplace until its adapter is implemented and tested.

The documented Portals NFT search response does not include seller username, seller rating, or last-seen time. Those details can only be displayed when a source actually supplies them; they will not be invented.

Portals Partner API access may require selecting a plan in the Portals mini app. The documented free plan is 1 request per second; paid plans cost GRAM.

## Setup
1. Create a Telegram bot with @BotFather and copy its token.
2. If testing Portals, obtain the Partner API key from the Portals mini app (Profile → Partner API).
3. Deploy this repository as a Render Background Worker using `render.yaml`.
4. Set `BOT_TOKEN`. Set `PORTALS_API_KEY` if you have access to Portals Partner API.
5. Add the bot to a Telegram supergroup with Topics enabled, make it an administrator with **Manage Topics**, then run `/setup`.
6. Every user must open the bot and press `/start` before the bot can send a private reservation log.

## Render
The included blueprint uses a paid Background Worker and persistent disk so polling continues and SQLite survives restarts. A free Render web service may sleep and is not suitable for reliable 24/7 polling.

## Local run
```bash
pip install -r requirements.txt
export BOT_TOKEN="..."
python bot.py
```
