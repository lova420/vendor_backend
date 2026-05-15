from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.deps import get_current_vendor
from app.core.qr import FORMAT_MIME, QrFormat, qr_url, render, slug_name
from app.models.vendor import Vendor

router = APIRouter(prefix="/vendor/qr", tags=["vendor:qr"])


@router.get("/info")
async def my_qr_info(
    vendor: Vendor = Depends(get_current_vendor),
) -> dict[str, str]:
    return {
        "vendor_id": str(vendor.id),
        "vendor_name": vendor.name,
        "url": qr_url(vendor.id),
    }


@router.get("/image")
async def my_qr_image(
    vendor: Vendor = Depends(get_current_vendor),
    format: QrFormat = Query("png"),
    download: bool = Query(False),
) -> Response:
    body = render(qr_url(vendor.id), format)
    headers = {}
    if download:
        filename = f"qr-{slug_name(vendor.name)}-{vendor.id}.{format}"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=body, media_type=FORMAT_MIME[format], headers=headers)
