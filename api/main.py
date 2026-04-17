from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from neo4j import AsyncGraphDatabase
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from config import settings

driver = None

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global driver
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_lifetime=3600,
        max_connection_pool_size=50,
    )
    await driver.verify_connectivity()
    yield
    await driver.close()


app = FastAPI(
    title="HunterLeech API",
    description="Plataforma de inteligencia anticorrupcion para Colombia",
    version="0.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from routers.health import router as health_router           # noqa: E402
from routers.search import router as search_router           # noqa: E402
from routers.contractors import router as contractors_router  # noqa: E402
from routers.contracts import router as contracts_router     # noqa: E402
from routers.graph import router as graph_router             # noqa: E402
from routers.empresas import router as empresas_router       # noqa: E402
from routers.sancionados import router as sancionados_router # noqa: E402
from routers.alertas import router as alertas_router         # noqa: E402

app.include_router(health_router, prefix="")
app.include_router(search_router, prefix="/api/v1")
app.include_router(contractors_router, prefix="/api/v1")
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(empresas_router, prefix="/api/v1")
app.include_router(sancionados_router, prefix="/api/v1")
app.include_router(alertas_router, prefix="/api/v1")
