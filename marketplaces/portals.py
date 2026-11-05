import logging
import os
from collections import Counter

import aiohttp

from .base import Marketplace

BASE_URL = "https://portal-market.com/partners"
log = logging.getLogger("gift-radar.portals")


class PortalsMarketplace(Marketplace):
    name = "portals"

    def __init__(self):
        self.api_key = os.getenv("PORTALS_API_KEY", "").strip()

    async def fetch_listings(self) -> list[dict]:
        if not self.api_key:
            log.warning("Portals API key is missing (PORTALS_API_KEY is empty)")
            return []

        headers = {"Authorization": f"partners {self.api_key}"}
        timeout = aiohttp.ClientTimeout(total=25)
        params = {
            "status": "listed",
            "limit": 100,
            "offset": 0,
            "sort_by": "listed_at desc",
        }

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(f"{BASE_URL}/nfts/search", params=params) as resp:
                log.info("Portals API response status: %s", resp.status)
                if resp.status in (401, 403):
                    body = await resp.text()
                    # Do not log request headers or API keys.
                    raise RuntimeError(
                        f"Portals API access error {resp.status}: {body[:300]}"
                    )
                resp.raise_for_status()
                payload = await resp.json()

        if not isinstance(payload, dict):
            log.warning("Portals API returned unexpected JSON type: %s", type(payload).__name__)
            return []

        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            log.warning(
                "Portals API response has non-list 'results'; response keys: %s",
                list(payload.keys())[:30],
            )
            return []

        statuses = Counter(
            str(item.get("status", "<missing>"))
            for item in raw_results
            if isinstance(item, dict)
        )
        log.info(
            "Portals API parsed response: total_count=%s, results_count=%s, statuses=%s",
            payload.get("total_count", "<missing>"),
            len(raw_results),
            dict(statuses),
        )
        if raw_results and isinstance(raw_results[0], dict):
            log.info("Portals first listing fields: %s", list(raw_results[0].keys())[:40])

        results = []
        skipped_currency = 0
        skipped_fields = 0
        for item in raw_results:
            if not isinstance(item, dict):
                skipped_fields += 1
                continue

            # Portals returns GRAM prices. Keep them labeled as GRAM; the
            # publisher currently only categorizes TON-denominated listings.
            price = item.get("price")
            tg_id = item.get("tg_id")
            if price is None or not tg_id or item.get("status") != "listed":
                skipped_fields += 1
                continue
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                skipped_fields += 1
                continue

            results.append({
                "source": self.name,
                "source_id": str(item.get("id") or tg_id),
                "title": f"{item.get('name', 'NFT Gift')} #{item.get('external_collection_number', '?')}",
                "price": price_value,
                "currency": "GRAM",
                "lot_url": f"https://t.me/nft/{tg_id}",
                "image_url": item.get("photo_url"),
                "seller_url": None,
                "raw": item,
            })

        log.info(
            "Portals adapter result: %s listings; skipped=%s (non-TON currency listings=%s)",
            len(results),
            skipped_fields,
            skipped_currency,
        )
        return results
