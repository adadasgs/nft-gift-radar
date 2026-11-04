import os
import aiohttp
from .base import Marketplace

BASE_URL = "https://portal-market.com/partners"

class PortalsMarketplace(Marketplace):
    name = "portals"

    def __init__(self):
        self.api_key = os.getenv("PORTALS_API_KEY", "").strip()
        self.session = None

    async def fetch_listings(self) -> list[dict]:
        if not self.api_key:
            return []
        headers = {"Authorization": f"partners {self.api_key}"}
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            params = {"status": "listed", "limit": 100, "offset": 0, "sort_by": "listed_at desc"}
            async with session.get(f"{BASE_URL}/nfts/search", params=params) as resp:
                if resp.status in (401, 403):
                    body = await resp.text()
                    raise RuntimeError(f"Portals API access error {resp.status}: {body[:300]}")
                resp.raise_for_status()
                payload = await resp.json()

        results = []
        for item in payload.get("results", []):
            # Portals documents prices in GRAM, not TON. Do not mislabel GRAM as TON.
            # Until an authoritative live GRAM/TON conversion is configured, skip this source
            # rather than placing a gift in a misleading TON price category.
            price = item.get("price")
            tg_id = item.get("tg_id")
            if not price or not tg_id or item.get("status") != "listed":
                continue
            try:
                price_value = float(price)
            except (TypeError, ValueError):
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
        return results
