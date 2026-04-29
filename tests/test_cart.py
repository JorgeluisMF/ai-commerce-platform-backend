import uuid
from collections.abc import Generator
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import UserRole
from app.services.user_service import create_user

SQLALCHEMY_TEST_DATABASE_URL = "sqlite+pysqlite://"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _customer_token(client: TestClient) -> str:
    suffix = uuid.uuid4().hex[:12]
    email = f"cart_{suffix}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Cart Customer",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_cart_forbidden_for_admin() -> None:
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        create_user(
            db,
            email="cart_admin@example.com",
            password="AdminPass1",
            full_name="Admin",
            role=UserRole.admin,
        )
    finally:
        db.close()

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "cart_admin@example.com", "password": "AdminPass1"},
    )
    token = login.json()["access_token"]

    response = client.get("/api/v1/cart", headers=_bearer(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    app.dependency_overrides.clear()


def test_get_cart_empty_returns_items_and_zero_subtotal() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    response = client.get("/api/v1/cart", headers=_bearer(token))
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["subtotal"] == "0.00"
    app.dependency_overrides.clear()


def test_checkout_empty_cart_returns_400() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    response = client.post("/api/v1/cart/checkout", headers=_bearer(token))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_cart"
    app.dependency_overrides.clear()


def test_checkout_happy_path_decrements_stock_and_creates_order() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Checkout Item",
            "description": "D",
            "sku": "cart_chk_001",
            "price": "19.99",
            "stock": 10,
            "is_active": True,
        },
    )
    assert create_product.status_code == 201
    product_id = create_product.json()["id"]

    add = client.post(
        "/api/v1/cart/items",
        headers=_bearer(token),
        json={"product_id": product_id, "quantity": 3},
    )
    assert add.status_code == 201
    cart = add.json()
    assert Decimal(cart["subtotal"]) == Decimal("59.97")

    checkout = client.post("/api/v1/cart/checkout", headers=_bearer(token))
    assert checkout.status_code == 201
    order = checkout.json()
    assert order["status"] == "pending"
    assert order["currency"] == "USD"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 3
    assert order["items"][0]["product_id"] == product_id
    assert Decimal(order["total_amount"]) == Decimal("59.97")

    prod_after = client.get(f"/api/v1/products/{product_id}")
    assert prod_after.json()["stock"] == 7

    cart_empty = client.get("/api/v1/cart", headers=_bearer(token))
    assert cart_empty.json()["items"] == []

    app.dependency_overrides.clear()


def test_checkout_insufficient_stock_returns_409() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Low Stock",
            "description": "D",
            "sku": "cart_low_001",
            "price": "5.00",
            "stock": 2,
            "is_active": True,
        },
    )
    pid = create_product.json()["id"]

    client.post(
        "/api/v1/cart/items",
        headers=_bearer(token),
        json={"product_id": pid, "quantity": 2},
    )

    db = TestingSessionLocal()
    try:
        from app.models.product import Product

        p = db.get(Product, pid)
        assert p is not None
        p.stock = 1
        db.commit()
    finally:
        db.close()

    checkout = client.post("/api/v1/cart/checkout", headers=_bearer(token))
    assert checkout.status_code == 409
    assert checkout.json()["error"]["code"] == "insufficient_stock"

    app.dependency_overrides.clear()


def test_checkout_price_changed_when_enforcement_enabled(monkeypatch) -> None:
    monkeypatch.setenv("CHECKOUT_REJECT_ON_PRICE_MISMATCH", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Price Will Change",
            "description": "D",
            "sku": "cart_px_001",
            "price": "10.00",
            "stock": 10,
            "is_active": True,
        },
    )
    pid = create_product.json()["id"]

    client.post(
        "/api/v1/cart/items",
        headers=_bearer(token),
        json={"product_id": pid, "quantity": 1},
    )

    db = TestingSessionLocal()
    try:
        from decimal import Decimal

        from app.models.product import Product

        p = db.get(Product, pid)
        assert p is not None
        p.price = Decimal("11.00")
        db.commit()
    finally:
        db.close()

    checkout = client.post("/api/v1/cart/checkout", headers=_bearer(token))
    assert checkout.status_code == 409
    err = checkout.json()["error"]
    assert err["code"] == "price_changed"
    assert pid in err["details"]["product_ids"]

    monkeypatch.delenv("CHECKOUT_REJECT_ON_PRICE_MISMATCH", raising=False)
    get_settings.cache_clear()
    app.dependency_overrides.clear()


def test_patch_foreign_cart_item_returns_404() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "cart_user_a@example.com",
            "password": "password123",
            "full_name": "User A",
        },
    )
    token_a = client.post(
        "/api/v1/auth/login",
        json={"email": "cart_user_a@example.com", "password": "password123"},
    ).json()["access_token"]

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "cart_user_b@example.com",
            "password": "password123",
            "full_name": "User B",
        },
    )
    token_b = client.post(
        "/api/v1/auth/login",
        json={"email": "cart_user_b@example.com", "password": "password123"},
    ).json()["access_token"]

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Shared",
            "description": "D",
            "sku": "cart_own_001",
            "price": "1.00",
            "stock": 50,
            "is_active": True,
        },
    )
    pid = create_product.json()["id"]

    add_a = client.post(
        "/api/v1/cart/items",
        headers=_bearer(token_a),
        json={"product_id": pid, "quantity": 1},
    )
    fake_other_line_id = uuid.uuid4()
    patch = client.patch(
        f"/api/v1/cart/items/{fake_other_line_id}",
        headers=_bearer(token_b),
        json={"quantity": 5},
    )
    assert patch.status_code == 404

    line_id = add_a.json()["items"][0]["id"]
    patch_other = client.patch(
        f"/api/v1/cart/items/{line_id}",
        headers=_bearer(token_b),
        json={"quantity": 5},
    )
    assert patch_other.status_code == 404

    app.dependency_overrides.clear()
