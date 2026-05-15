from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.rate_limit import limiter
from app.database import _verify_ca_cert, engine
from app.routes import (
    admin_dashboard,
    admin_qr,
    admin_vendors,
    auth as auth_routes,
    public as public_routes,
    redirects as redirect_routes,
    vendor_cars,
    vendor_customers,
    vendor_dashboard,
    vendor_qr,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast if the CA cert is missing/invalid.
    _verify_ca_cert()
    yield
    await engine.dispose()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.ENVIRONMENT == "production":
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response


app = FastAPI(
    title="MagickVoice — Multi-Vendor Lead Management",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


app.include_router(auth_routes.router)
app.include_router(admin_vendors.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_qr.router)
app.include_router(vendor_customers.router)
app.include_router(vendor_cars.router)
app.include_router(vendor_dashboard.router)
app.include_router(vendor_qr.router)
app.include_router(public_routes.router)
app.include_router(redirect_routes.router)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})
