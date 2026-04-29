import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_role
from app.api.deps.global_rate_limit import enforce_global_rate_limit
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories import review_repository
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductSemanticResult,
    ProductSemanticSearchResponse,
    ProductUpdate,
    SemanticSearchPaginationMeta,
)
from app.services.product_image_service import add_product_image, delete_product_image, to_product_response
from app.services.product_service import (
    DuplicateSKUError,
    ProductConcurrencyError,
    ProductNotFoundError,
    create_product,
    get_product_by_id,
    list_products,
    update_product,
)
from app.services.audit_service import (
    client_ip_from_request,
    persist_audit_record,
    user_agent_from_request,
)
from app.services.semantic_search_service import semantic_search_products
from app.services.semantic_search_service import EmbeddingsStoreNotReadyError

router = APIRouter(prefix="/products", tags=["products"])

_limit_products_list = enforce_global_rate_limit("products_list")
_limit_products_write = enforce_global_rate_limit("products_write")
_limit_products_semantic = enforce_global_rate_limit("products_semantic")


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
)
def create_product_endpoint(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_limit_products_write),
) -> ProductResponse:
    try:
        product = create_product(db=db, payload=payload)
        return to_product_response(product, average_rating=0.0, reviews_count=0)
    except DuplicateSKUError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=ProductListResponse, summary="List products")
def list_products_endpoint(
    _: None = Depends(_limit_products_list),
    db: Session = Depends(get_db),
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=120),
) -> ProductListResponse:
    if page is not None:
        effective_limit = page_size
        effective_offset = (page - 1) * page_size
        items, total = list_products(
            db=db,
            limit=effective_limit,
            offset=effective_offset,
            is_active=is_active,
            search=search,
        )
        stats = review_repository.get_product_review_stats(db, [item.id for item in items])
        return ProductListResponse(
            items=[
                to_product_response(
                    item,
                    average_rating=stats.get(item.id, (0.0, 0))[0],
                    reviews_count=stats.get(item.id, (0.0, 0))[1],
                )
                for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    eff_limit = limit if limit is not None else 20
    items, total = list_products(
        db=db,
        limit=eff_limit,
        offset=offset,
        is_active=is_active,
        search=search,
    )
    stats = review_repository.get_product_review_stats(db, [item.id for item in items])
    derived_page = (offset // eff_limit) + 1 if eff_limit else 1
    return ProductListResponse(
        items=[
            to_product_response(
                item,
                average_rating=stats.get(item.id, (0.0, 0))[0],
                reviews_count=stats.get(item.id, (0.0, 0))[1],
            )
            for item in items
        ],
        total=total,
        page=derived_page,
        page_size=eff_limit,
    )


@router.post(
    "/{product_id}/images",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload product image (admin)",
)
async def upload_product_image_endpoint(
    product_id: int,
    db: Session = Depends(get_db),
    file: UploadFile = File(description="JPEG, PNG, or WebP image"),
    _admin: User = Depends(require_role(UserRole.admin)),
) -> ProductResponse:
    settings = get_settings()
    data = await file.read()
    return add_product_image(
        db,
        product_id=product_id,
        data=data,
        content_type=file.content_type,
        settings=settings,
    )


@router.delete(
    "/{product_id}/images/{image_id}",
    response_model=ProductResponse,
    summary="Delete product image (admin)",
)
def delete_product_image_endpoint(
    product_id: int,
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
) -> ProductResponse:
    return delete_product_image(db, product_id=product_id, image_id=image_id)


@router.get("/search/semantic", response_model=ProductSemanticSearchResponse, summary="Semantic search")
def semantic_search_products_endpoint(
    _: None = Depends(_limit_products_semantic),
    q: str = Query(min_length=2, max_length=500, description="Natural language search query"),
    limit: int = Query(default=5, ge=1, le=50),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
) -> ProductSemanticSearchResponse:
    settings = get_settings()
    if not settings.embeddings_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic search is disabled. Enable EMBEDDINGS_ENABLED=true.",
        )

    try:
        rows = semantic_search_products(db=db, query_text=q.strip(), limit=limit, is_active=is_active)
    except EmbeddingsStoreNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    items = []
    for row in rows:
        pdata = {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "sku": row["sku"],
            "price": row["price"],
            "stock": row["stock"],
            "is_active": row["is_active"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "images": [],
            "average_rating": 0.0,
            "reviews_count": 0,
        }
        items.append(
            ProductSemanticResult(
                product=ProductResponse.model_validate(pdata),
                score=row["score"],
            )
        )
    total = len(items)
    page_size = limit
    pages = 0 if total == 0 else (total + page_size - 1) // page_size
    meta = SemanticSearchPaginationMeta(
        total=total,
        page=1,
        page_size=page_size,
        pages=pages,
    )
    return ProductSemanticSearchResponse(query=q, limit=limit, items=items, meta=meta)


@router.get("/{product_id}", response_model=ProductResponse, summary="Get product by id")
def get_product_endpoint(product_id: int, db: Session = Depends(get_db)) -> ProductResponse:
    try:
        product = get_product_by_id(db=db, product_id=product_id)
        stats = review_repository.get_product_review_stats(db, [product.id])
        average_rating, reviews_count = stats.get(product.id, (0.0, 0))
        return to_product_response(
            product,
            average_rating=average_rating,
            reviews_count=reviews_count,
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{product_id}", response_model=ProductResponse, summary="Patch product")
def patch_product_endpoint(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
    expected_updated_at: datetime | None = Query(
        default=None,
        description="Optimistic concurrency guard. Use last known updated_at.",
    ),
) -> ProductResponse:
    try:
        product = update_product(
            db=db,
            product_id=product_id,
            payload=payload,
            expected_updated_at=expected_updated_at,
        )
        ip = client_ip_from_request(request)
        ua = user_agent_from_request(request)
        background_tasks.add_task(
            persist_audit_record,
            action="product.updated",
            resource_type="product",
            resource_id=str(product_id),
            user_id=current_user.id,
            ip_address=ip,
            user_agent=ua,
        )
        stats = review_repository.get_product_review_stats(db, [product.id])
        average_rating, reviews_count = stats.get(product.id, (0.0, 0))
        return to_product_response(
            product,
            average_rating=average_rating,
            reviews_count=reviews_count,
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateSKUError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ProductConcurrencyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
