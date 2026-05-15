import io
import re
import uuid
from typing import Literal

import qrcode
import segno
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_role
from app.database import get_db
from app.models.user import UserType
from app.models.vendor import Vendor

router = APIRouter(
    prefix="/admin/qr",
    tags=["admin:qr"],
    dependencies=[Depends(require_role(UserType.SUPER_ADMIN))],
)


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9_-]+")


def _slug(name: str) -> str:
    cleaned = _FILENAME_SANITIZER.sub("-", name.strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "vendor"


def _qr_url(vendor_id: uuid.UUID) -> str:
    base = settings.HOSTING_ADDRESS.rstrip("/")
    return f"{base}/register?vendor_id={vendor_id}"


def _pil_qr(data: str):
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def _png_bytes(data: str) -> bytes:
    img = _pil_qr(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(data: str) -> bytes:
    img = _pil_qr(data).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _svg_bytes(data: str) -> bytes:
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=10, border=4, xmldecl=True, svgns=True)
    return buf.getvalue()


_FORMAT_MIME = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}


@router.get("/{vendor_id}")
async def generate_qr(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    format: Literal["png", "jpeg", "svg"] = Query("png"),
    download: bool = Query(False),
) -> Response:
    stmt = select(Vendor).where(
        Vendor.id == vendor_id, Vendor.is_deleted.is_(False)
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
        )

    url = _qr_url(vendor.id)
    if format == "png":
        body = _png_bytes(url)
    elif format == "jpeg":
        body = _jpeg_bytes(url)
    else:
        body = _svg_bytes(url)

    headers = {}
    if download:
        filename = f"qr-{_slug(vendor.name)}-{vendor.id}.{format}"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return Response(content=body, media_type=_FORMAT_MIME[format], headers=headers)


@router.get("/{vendor_id}/info")
async def qr_info(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Returns the URL the QR encodes — useful for previewing the destination."""
    stmt = select(Vendor.id, Vendor.name).where(
        Vendor.id == vendor_id, Vendor.is_deleted.is_(False)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
        )
    return {
        "vendor_id": str(row.id),
        "vendor_name": row.name,
        "url": _qr_url(row.id),
    }
