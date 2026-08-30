from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ais, ais_stream, attribution, attribution_demo, detections, detections_demo
from app.config import settings

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "End-to-end pipeline for marine oil spill detection, drift modelling, "
        "and vessel attribution via SAR imagery and AIS telemetry."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIRouters are mounted here. Order matters: specific routes before /health
# is not required, but keep detection routes grouped for readability.
app.include_router(detections_demo.router, prefix="/api/v1/detections", tags=["detections-demo"])
app.include_router(detections.router, prefix="/api/v1/detections", tags=["detections"])
app.include_router(attribution_demo.router, prefix="/api/v1/attribution", tags=["attribution-demo"])
app.include_router(attribution.router, prefix="/api/v1/attribution", tags=["attribution"])
app.include_router(ais.router, prefix="/api/v1/ais", tags=["ais"])
app.include_router(ais_stream.router, prefix="/api/v1/ais", tags=["ais-stream"])


@app.on_event("startup")
def _startup():
    """Initialize database and optionally start the AIS feed client."""
    from app.core.db import init_db
    init_db()
    # Optionally start the background feed client
    if settings.AIS_FEED_URL:
        from app.ais.feed import get_feed_client
        client = get_feed_client()
        client.start()


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"], include_in_schema=False)
def health() -> dict:
    from app.core.db import get_db
    db_stats = get_db().get_stats()
    return {"status": "ok", "version": settings.API_VERSION, "db": db_stats}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"message": settings.API_TITLE, "docs": "/docs"}
