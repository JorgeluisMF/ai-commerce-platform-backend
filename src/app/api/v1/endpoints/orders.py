import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, joinedload

from app.db.redis import get_redis_client
from app.api.deps.auth import require_role
from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.db.session import get_db
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.order import (
    OrderDetailResponse,
    OrderStatusPatchRequest,
    UserOrderListResponse,
)

from app.services import order_service
from app.services.audit_service import (
    client_ip_from_request,
    persist_audit_record,
    user_agent_from_request,
)
from app.services.idempotency_service import (
    compute_key,
    get_cached_response,
    set_cached_response,
)


router = APIRouter(prefix="/orders", tags=["orders"])





@router.get("", response_model=UserOrderListResponse, summary="List current user's orders")

def list_my_orders(

    db: Session = Depends(get_db),  # noqa: B008

    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008

    page: int = Query(default=1, ge=1),

    page_size: int = Query(default=20, ge=1, le=100),

    order_status: str | None = Query(default=None, alias="status"),

) -> UserOrderListResponse:

    rows, total = order_service.list_orders_for_user(

        db,

        user_id=current_user.id,

        page=page,

        page_size=page_size,

        status_filter=order_status,

    )

    return UserOrderListResponse(

        items=[order_service.order_list_item(o) for o in rows],

        total=total,

        page=page,

        page_size=page_size,

    )





@router.get("/{order_id}", response_model=OrderDetailResponse, summary="Get order detail")

def get_my_order(

    order_id: uuid.UUID,

    db: Session = Depends(get_db),  # noqa: B008

    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008

) -> OrderDetailResponse:

    order = order_service.get_order_detail_for_user(

        db, user_id=current_user.id, order_id=order_id

    )

    return order_service.order_to_detail_response(db, order)





@router.patch(

    "/{order_id}/status",

    response_model=OrderDetailResponse,

    summary="Update order status (admin)",

)

def admin_patch_order_status(

    order_id: uuid.UUID,

    payload: OrderStatusPatchRequest,

    request: Request,

    background_tasks: BackgroundTasks,

    db: Session = Depends(get_db),  # noqa: B008

    admin: User = Depends(require_role(UserRole.admin)),  # noqa: B008

) -> OrderDetailResponse:

    try:

        new_status = OrderStatus(payload.status)

    except ValueError:

        raise_api_error(

            code="invalid_order_status",

            message="Invalid order status value.",

            status_code=status.HTTP_400_BAD_REQUEST,

        )

    order_service.admin_update_order_status(db, order_id=order_id, new_status=new_status)

    full = (

        db.query(Order)

        .filter(Order.id == order_id)

        .options(joinedload(Order.items))

        .first()

    )

    assert full is not None

    ip = client_ip_from_request(request)

    ua = user_agent_from_request(request)

    background_tasks.add_task(

        persist_audit_record,

        action="order.status_updated",

        resource_type="order",

        resource_id=str(order_id),

        user_id=admin.id,

        audit_metadata={"status": payload.status},

        ip_address=ip,

        user_agent=ua,

    )

    return order_service.order_to_detail_response(db, full)





@router.post(

    "/{order_id}/pay",

    response_model=OrderDetailResponse,

    summary="Simulated payment: mark pending order as paid",

)

def simulated_pay_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OrderDetailResponse:
    settings = get_settings()

    if not settings.simulated_payment_enabled:
        raise_api_error(
            code="simulated_payment_disabled",
            message="Simulated payment is disabled.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    cache_key: str | None = None
    redis_client = None
    raw_idem = (idempotency_key or "").strip()
    if raw_idem:
        try:
            cache_key = compute_key(current_user.id, raw_idem, f"order_pay:{order_id}")
            redis_client = get_redis_client()
            cached = get_cached_response(redis_client, cache_key)
            if cached:
                _, body = cached
                return OrderDetailResponse.model_validate(body)
        except ValueError:
            cache_key = None
            redis_client = None
        except RedisError:
            raise_api_error(
                code="redis_unavailable",
                message="Payment idempotency requires Redis; try again shortly.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    order_service.mark_order_paid_simulated(db, user_id=current_user.id, order_id=order_id)

    full = (
        db.query(Order)
        .filter(Order.id == order_id)
        .options(joinedload(Order.items))
        .first()
    )
    assert full is not None
    detail = order_service.order_to_detail_response(db, full)

    if cache_key is not None and redis_client is not None:
        set_cached_response(
            redis_client,
            cache_key,
            status_code=status.HTTP_200_OK,
            body=detail.model_dump(mode="json"),
            ttl_sec=settings.idempotency_ttl_sec,
        )
    return detail

