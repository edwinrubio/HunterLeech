from typing import AsyncGenerator
from functools import lru_cache
from neo4j import AsyncSession
import main
from config import settings
from middleware.privacy import PrivacyFilter


async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    async with main.driver.session(database="neo4j") as session:
        yield session


@lru_cache(maxsize=1)
def get_privacy_filter() -> PrivacyFilter:
    """Return a PrivacyFilter singleton bound to the current PUBLIC_MODE setting."""
    return PrivacyFilter(public_mode=settings.public_mode)
