from datetime import datetime
import logging

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.product import Product
from app.models.product_image import ProductImage
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.semantic_search_service import index_product_embedding

logger = logging.getLogger(__name__)


def _index_or_enqueue_embedding(db: Session, product: Product) -> None:
    settings = get_settings()
    if settings.embeddings_async:
        try:
            from app.services.queue_service import enqueue_embedding_index

            enqueue_embedding_index(product.id)
        except Exception:
            logger.exception("Embedding enqueue failed for product_id=%s", product.id)
        return
    try:
        index_product_embedding(db, product)
    except Exception:
        logger.exception("Embedding indexing failed for product_id=%s", product.id)


class DuplicateSKUError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class ProductConcurrencyError(Exception):
    pass


def create_product(db: Session, payload: ProductCreate) -> Product:
    product = Product(
        name=payload.name,
        description=payload.description,
        sku=payload.sku,
        price=payload.price,
        stock=payload.stock,
        is_active=payload.is_active,
    )

    db.add(product)

    try:
        db.flush()
        for idx, url in enumerate(payload.images):
            db.add(
                ProductImage(
                    product_id=product.id,
                    storage_key=url,
                    sort_order=idx,
                    is_primary=(idx == 0),
                )
            )
        db.commit()
        _index_or_enqueue_embedding(db, product)
        return get_product_by_id(db, product.id)
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateSKUError("Product with this SKU already exists.") from exc


def list_products(
    db: Session,
    *,
    limit: int,
    offset: int,
    is_active: bool | None = None,
    search: str | None = None,
) -> tuple[list[Product], int]:
    query = db.query(Product).options(selectinload(Product.images))
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(term),
                Product.sku.ilike(term),
                Product.description.ilike(term),
            )
        )

    total = query.count()
    items = (
        query.order_by(Product.created_at.desc(), Product.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def get_product_by_id(db: Session, product_id: int) -> Product:
    product = (
        db.query(Product)
        .options(selectinload(Product.images))
        .filter(Product.id == product_id)
        .first()
    )
    if product is None:
        raise ProductNotFoundError(f"Product with id={product_id} was not found.")
    return product


def update_product(
    db: Session,
    *,
    product_id: int,
    payload: ProductUpdate,
    expected_updated_at: datetime | None = None,
) -> Product:
    product = get_product_by_id(db, product_id)

    if expected_updated_at is not None and product.updated_at != expected_updated_at:
        raise ProductConcurrencyError("Product was modified by another process. Reload and retry.")

    updates = payload.model_dump(exclude_unset=True)
    images = updates.pop("images", None)
    for field_name, value in updates.items():
        setattr(product, field_name, value)
    if images is not None:
        product.images.clear()
        for idx, url in enumerate(images):
            product.images.append(
                ProductImage(
                    product_id=product.id,
                    storage_key=url,
                    sort_order=idx,
                    is_primary=(idx == 0),
                )
            )

    try:
        db.add(product)
        db.commit()
        _index_or_enqueue_embedding(db, product)
        return get_product_by_id(db, product_id)
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateSKUError("Product with this SKU already exists.") from exc
