from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes.estimates import router as estimates_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.errors import error_response, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.rate_limit import limiter

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="STL Estimator API",
    version="1.0.0",
    description="Production-ready MVP API for analyzing STL files and returning geometry-based estimates.",
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda _request, _exc: error_response(
        429,
        "RATE_LIMIT_EXCEEDED",
        "Too many requests. Please try again later.",
    ),
)

app.middleware("http")(request_context_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["X-API-Key", "X-Request-ID", "Content-Type"],
)
app.add_middleware(SlowAPIMiddleware)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(estimates_router)
