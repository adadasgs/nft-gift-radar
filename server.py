import asyncio
import logging
import os

from aiohttp import web

from bot import main as run_bot

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gift-radar.server")


async def health(_request):
    return web.json_response({"status": "ok", "service": "nft-gift-radar"})


async def start_bot(app):
    app["bot_task"] = asyncio.create_task(run_bot())


async def stop_bot(app):
    task = app.get("bot_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = web.Application()
app.router.add_get("/", health)
app.router.add_get("/health", health)
app.on_startup.append(start_bot)
app.on_cleanup.append(stop_bot)


if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
