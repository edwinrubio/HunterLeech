from fastapi import APIRouter, Depends
from neo4j import AsyncSession
from dependencies import get_neo4j_session

router = APIRouter()


@router.get("/health")
async def health(session: AsyncSession = Depends(get_neo4j_session)):
    """Liveness and Neo4j connectivity check."""
    result = await session.run("RETURN 1 AS ok")
    record = await result.single()
    return {
        "status": "ok",
        "neo4j": "connected" if record and record["ok"] == 1 else "error",
    }
