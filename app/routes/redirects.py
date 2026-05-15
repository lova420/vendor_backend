import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_ip
from app.database import get_db
from app.models.scan_event import ScanEvent
from app.models.vendor import Vendor

router = APIRouter(tags=["redirects"])
log = logging.getLogger(__name__)


async def _log_scan(
    db: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    request: Request,
) -> None:
    """Best-effort scan logging. Never fails the parent request."""
    try:
        ip = get_remote_address(request) or "0.0.0.0"
        ua = request.headers.get("user-agent")
        if ua and len(ua) > 512:
            ua = ua[:512]
        db.add(ScanEvent(vendor_id=vendor_id, ip_hash=hash_ip(ip), user_agent=ua))
        await db.commit()
    except Exception:  # pragma: no cover - analytics must not break UX
        await db.rollback()
        log.warning("scan_event_log_failed", exc_info=True)


@router.get("/register")
async def qr_register_redirect(
    request: Request,
    db: AsyncSession = Depends(get_db),
    vendor_id: str | None = Query(None),
) -> RedirectResponse:
    """QR landing endpoint.

    The QR encodes ``{HOSTING_ADDRESS}/register?vendor_id=...`` (the backend
    URL), so every scan hits this endpoint exactly once — the scan_event row
    is written here, then we 302 to the frontend's register page. That way
    the count reflects real scans, not lazy client-side fetches that can be
    skipped by bots or interrupted browsers.
    """
    vendor_uuid: uuid.UUID | None = None
    if vendor_id:
        try:
            vendor_uuid = uuid.UUID(vendor_id)
        except ValueError:
            vendor_uuid = None

    if vendor_uuid is not None:
        stmt = select(Vendor.id).where(
            Vendor.id == vendor_uuid, Vendor.is_deleted.is_(False)
        )
        if (await db.execute(stmt)).first() is not None:
            await _log_scan(db, vendor_id=vendor_uuid, request=request)
        # If the vendor doesn't exist we deliberately skip logging so bogus
        # links can't pollute scan counts, but we still redirect — the
        # frontend already renders a consistent "invalid QR" screen.

    # Pass the original ?vendor_id through unchanged (even if malformed) so
    # the frontend, not the backend, owns the error UX.
    query = urlencode({"vendor_id": vendor_id}) if vendor_id else ""
    target_base = settings.FRONTEND_ORIGIN.rstrip("/")
    target = f"{target_base}/register{'?' + query if query else ''}"
    return RedirectResponse(target, status_code=302)
