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
    email = f"ord_{suffix}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Buyer"},
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_orders_list_and_detail_after_checkout() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    pid = client.post(
        "/api/v1/products",
        json={
            "name": "Order Test Item",
            "description": "D",
            "sku": f"ord_sku_{uuid.uuid4().hex[:8]}",
            "price": "10.00",
            "stock": 5,
            "is_active": True,
        },
    ).json()["id"]

    client.post(
        "/api/v1/cart/items",
        headers=_bearer(token),
        json={"product_id": pid, "quantity": 2},
    )
    checkout = client.post("/api/v1/cart/checkout", headers=_bearer(token))
    assert checkout.status_code == 201
    order_id = checkout.json()["order_id"]

    lst = client.get("/api/v1/orders?page=1&page_size=10", headers=_bearer(token))
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == order_id

    detail = client.get(f"/api/v1/orders/{order_id}", headers=_bearer(token))
    assert detail.status_code == 200
    d = detail.json()
    assert d["status"] == "pending"
    assert Decimal(d["total_amount"]) == Decimal("20.00")

    app.dependency_overrides.clear()


def test_admin_transition_order_status() -> None:
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        create_user(
            db,
            email="orders_admin@test.com",
            password="AdminPass1",
            full_name="Admin",
            role=UserRole.admin,
        )
    finally:
        db.close()

    client = TestClient(app)

    cust_tok = _customer_token(client)
    pid = client.post(
        "/api/v1/products",
        json={
            "name": "Pay Item",
            "description": "D",
            "sku": f"pay_{uuid.uuid4().hex[:8]}",
            "price": "5.00",
            "stock": 10,
            "is_active": True,
        },
    ).json()["id"]

    client.post(
        "/api/v1/cart/items",
        headers=_bearer(cust_tok),
        json={"product_id": pid, "quantity": 1},
    )
    oid = client.post("/api/v1/cart/checkout", headers=_bearer(cust_tok)).json()["order_id"]

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "orders_admin@test.com", "password": "AdminPass1"},
    )
    admin_headers = _bearer(admin_login.json()["access_token"])

    patch = client.patch(
        f"/api/v1/orders/{oid}/status",
        headers=admin_headers,
        json={"status": "paid"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "paid"

    ship = client.patch(
        f"/api/v1/orders/{oid}/status",
        headers=admin_headers,
        json={"status": "shipped"},
    )
    assert ship.status_code == 200

    app.dependency_overrides.clear()


def test_simulated_pay_marks_pending_paid() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = _customer_token(client)

    pid = client.post(
        "/api/v1/products",
        json={
            "name": "Mock Pay Item",
            "description": "D",
            "sku": f"mck_{uuid.uuid4().hex[:8]}",
            "price": "3.00",
            "stock": 3,
            "is_active": True,
        },
    ).json()["id"]

    client.post(
        "/api/v1/cart/items",
        headers=_bearer(token),
        json={"product_id": pid, "quantity": 1},
    )
    oid = client.post("/api/v1/cart/checkout", headers=_bearer(token)).json()["order_id"]

    pay = client.post(f"/api/v1/orders/{oid}/pay", headers=_bearer(token))
    assert pay.status_code == 200
    assert pay.json()["status"] == "paid"

    pay_again = client.post(f"/api/v1/orders/{oid}/pay", headers=_bearer(token))
    assert pay_again.status_code == 200
    assert pay_again.json()["status"] == "paid"

    app.dependency_overrides.clear()


def test_products_page_query_returns_paged_shape() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    client.post(
        "/api/v1/products",
        json={
            "name": "Paged A",
            "description": "D",
            "sku": f"pga_{uuid.uuid4().hex[:8]}",
            "price": "1.00",
            "stock": 1,
            "is_active": True,
        },
    )

    r = client.get("/api/v1/products?page=1&page_size=5")
    assert r.status_code == 200
    data = r.json()
    assert "pages" in data
    assert data["page"] == 1
    assert data["page_size"] == 5

    app.dependency_overrides.clear()
