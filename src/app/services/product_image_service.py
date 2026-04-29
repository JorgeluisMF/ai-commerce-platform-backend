"""Product image uploads and URL resolution."""

from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.http_exceptions import raise_api_error
from app.models.product import Product
from app.models.product_image import ProductImage
from app.schemas.product import ProductResponse
from app.storage.factory import get_storage_backend


_ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _ordered_images(product: Product) -> list[ProductImage]:
    return sorted(product.images, key=lambda im: (im.sort_order, str(im.id)))


def _is_absolute_url(storage_key: str) -> bool:
    return storage_key.startswith("http://") or storage_key.startswith("https://")


def image_urls_for_product(product: Product) -> list[str]:
    storage = get_storage_backend()
    urls: list[str] = []
    for im in _ordered_images(product):
        key = im.storage_key
        urls.append(key if _is_absolute_url(key) else storage.public_url(key))
    return urls


def to_product_response(
    product: Product,
    *,
    average_rating: float = 0.0,
    reviews_count: int = 0,
) -> ProductResponse:
    urls = image_urls_for_product(product)
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        sku=product.sku,
        price=product.price,
        stock=product.stock,
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
        images=urls,
        average_rating=average_rating,
        reviews_count=reviews_count,
    )


def add_product_image(
    db: Session,
    *,
    product_id: int,
    data: bytes,
    content_type: str | None,
    settings: Settings,
) -> ProductResponse:
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = _ALLOWED_TYPES.get(ctype)
    if ext is None:
        raise_api_error(
            code="invalid_image_type",
            message="Only JPEG, PNG, and WebP images are allowed.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(data) > settings.product_image_max_bytes:
        raise_api_error(
            code="image_too_large",
            message="Image exceeds maximum allowed size.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"max_bytes": settings.product_image_max_bytes},
        )

    product = db.get(Product, product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message="Product was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    storage = get_storage_backend()
    storage_key = storage.put(product_id=product_id, data=data, extension=ext)

    max_sort = (
        db.query(sa_func.coalesce(sa_func.max(ProductImage.sort_order), -1))
        .filter(ProductImage.product_id == product_id)
        .scalar()
    )
    next_sort = int(max_sort or -1) + 1
    existing_count = (
        db.query(sa_func.count())
        .select_from(ProductImage)
        .filter(ProductImage.product_id == product_id)
        .scalar()
        or 0
    )
    make_primary = existing_count == 0

    if make_primary:
        db.query(ProductImage).filter(ProductImage.product_id == product_id).update(
            {ProductImage.is_primary: False}
        )

    row = ProductImage(
        product_id=product_id,
        storage_key=storage_key,
        sort_order=next_sort,
        is_primary=make_primary,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise

    loaded = (
        db.query(Product)
        .filter(Product.id == product_id)
        .options(selectinload(Product.images))
        .first()
    )
    assert loaded is not None
    return to_product_response(loaded)


def delete_product_image(
    db: Session,
    *,
    product_id: int,
    image_id: uuid.UUID,
) -> ProductResponse:
    img = (
        db.query(ProductImage)
        .filter(ProductImage.id == image_id, ProductImage.product_id == product_id)
        .first()
    )
    if img is None:
        raise_api_error(
            code="image_not_found",
            message="Product image was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    storage = get_storage_backend()
    key = img.storage_key
    was_primary = img.is_primary

    others = (
        db.query(ProductImage)
        .filter(ProductImage.product_id == product_id, ProductImage.id != img.id)
        .order_by(ProductImage.sort_order, ProductImage.id)
        .all()
    )

    db.delete(img)

    if was_primary and others:
        others[0].is_primary = True
        db.add(others[0])

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    if not _is_absolute_url(key):
        storage.delete(key)

    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .options(selectinload(Product.images))
        .first()
    )
    assert product is not None
    return to_product_response(product)
