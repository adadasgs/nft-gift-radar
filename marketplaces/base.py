from abc import ABC, abstractmethod

class Marketplace(ABC):
    name: str

    @abstractmethod
    async def fetch_listings(self) -> list[dict]:
        """Return normalized listings. Prices must be denominated in TON."""
        raise NotImplementedError
