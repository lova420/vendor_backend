import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.core.qr import FORMAT_MIME, QrFormat, qr_url, render, slug_name
from app.database import get_db
from app.models.user import UserType
from app.models.vendor import Vendor

router = APIRouter(
    prefix="/admin/qr",
    tags=["admin:qr"],
    dependencies=[Depends(require_role(UserType.SUPER_ADMIN))],
)


@router.get("/{vendor_id}")
async def generate_qr(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    format: QrFormat = Query("png"),
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

    body = render(qr_url(vendor.id), format)

    headers = {}
    if download:
        filename = f"qr-{slug_name(vendor.name)}-{vendor.id}.{format}"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return Response(content=body, media_type=FORMAT_MIME[format], headers=headers)


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
        "url": qr_url(row.id),
    }
