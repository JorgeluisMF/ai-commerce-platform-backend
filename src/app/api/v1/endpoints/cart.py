import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_role
from app.db.redis import get_redis_client
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.cart import CartItemAddRequest, CartItemUpdateRequest, CartResponse
from app.schemas.order import CheckoutResponse
from app.services import cart_service, checkout_service
from app.services.queue_service import enqueue_post_checkout
from app.services.audit_service import (
    client_ip_from_request,
    persist_audit_record,
    user_agent_from_request,
)

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartResponse, summary="Get current shopping cart")
def get_cart(
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
) -> CartResponse:
    return cart_service.get_cart(db, current_user.id)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or merge a line in the cart",
)
def add_cart_item(
    payload: CartItemAddRequest,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
) -> CartResponse:
    return cart_service.add_cart_item(
        db,
        user_id=current_user.id,
        product_id=payload.product_id,
        quantity=payload.quantity,
    )


@router.patch(
    "/items/{cart_item_id}",
    response_model=CartResponse,
    summary="Update cart line quantity",
)
def update_cart_item(
    cart_item_id: uuid.UUID,
    payload: CartItemUpdateRequest,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
) -> CartResponse:
    return cart_service.update_cart_item(
        db,
        user_id=current_user.id,
        cart_item_id=cart_item_id,
        quantity=payload.quantity,
    )


@router.delete(
    "/items/{cart_item_id}",
    response_model=CartResponse,
    summary="Remove a cart line",
)
def remove_cart_item(
    cart_item_id: uuid.UUID,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
) -> CartResponse:
    return cart_service.remove_cart_item(
        db, user_id=current_user.id, cart_item_id=cart_item_id
    )


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Checkout: create order, decrement stock, clear cart",
)
def post_checkout(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(require_role(UserRole.customer)),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CheckoutResponse:
    redis_client = None
    if idempotency_key and idempotency_key.strip():
        redis_client = get_redis_client()
    resp = checkout_service.checkout(
        db,
        current_user.id,
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
        redis_client=redis_client,
    )
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)
    background_tasks.add_task(
        persist_audit_record,
        action="checkout.completed",
        resource_type="order",
        resource_id=str(resp.order_id),
        user_id=current_user.id,
        audit_metadata={"currency": resp.currency, "total_amount": str(resp.total_amount)},
        ip_address=ip,
        user_agent=ua,
    )
    try:
        enqueue_post_checkout(str(resp.order_id))
    except Exception:
        pass
    return resp
