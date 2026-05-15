"""Shared QR-rendering helpers.

Both the super-admin QR generator (`/admin/qr/...`) and the vendor's
self-service QR view (`/vendor/qr/...`) need to emit byte-identical QRs for
the same vendor — the encoded URL is what the printed QR points at, so any
divergence between the two views would silently produce QRs that resolve
differently. Keeping the URL builder and the renderers in one place is the
cheapest way to enforce that.
"""

from __future__ import annotations

import io
import re
import uuid
from typing import Literal

import qrcode
import segno

from app.config import settings

QrFormat = Literal["png", "jpeg", "svg"]

FORMAT_MIME: dict[QrFormat, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}

_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9_-]+")


def slug_name(name: str) -> str:
    cleaned = _FILENAME_SANITIZER.sub("-", name.strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "vendor"


def qr_url(vendor_id: uuid.UUID) -> str:
    """Build the URL that gets encoded into the QR.

    HOSTING_ADDRESS should be the *backend* origin — the backend's /register
    endpoint logs a scan_event and 302s the visitor to the frontend.
    """
    base = settings.HOSTING_ADDRESS.rstrip("/")
    return f"{base}/register?vendor_id={vendor_id}"


def _pil_qr(data: str):
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def png_bytes(data: str) -> bytes:
    img = _pil_qr(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(data: str) -> bytes:
    img = _pil_qr(data).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def svg_bytes(data: str) -> bytes:
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=10, border=4, xmldecl=True, svgns=True)
    return buf.getvalue()


def render(data: str, format: QrFormat) -> bytes:
    if format == "png":
        return png_bytes(data)
    if format == "jpeg":
        return jpeg_bytes(data)
    return svg_bytes(data)
