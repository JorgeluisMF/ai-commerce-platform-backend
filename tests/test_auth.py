from collections.abc import Generator

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


def test_register_success() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "email": "newuser@example.com",
        "password": "password123",
        "full_name": "New User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert data["role"] == "customer"
    assert data["is_active"] is True
    assert "id" in data
    app.dependency_overrides.clear()


def test_register_duplicate_email_returns_409() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "full_name": "First",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    second = client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "email_already_registered"
    app.dependency_overrides.clear()


def test_login_success_returns_token_and_expires_in() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "password123",
            "full_name": "Login User",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] >= 60
    app.dependency_overrides.clear()


def test_login_bad_password_returns_401() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "badlogin@example.com",
            "password": "password123",
            "full_name": "X",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "badlogin@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    app.dependency_overrides.clear()


def test_me_without_token_returns_401() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    app.dependency_overrides.clear()


def test_me_with_invalid_token_returns_401() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/api/v1/auth/me", headers=_bearer("not-a-real-jwt"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    app.dependency_overrides.clear()


def test_me_with_valid_token_returns_200() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "password123",
            "full_name": "Me User",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "password123"},
    )
    token = login.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers=_bearer(token))
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    app.dependency_overrides.clear()


def test_patch_product_forbidden_for_customer() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Item",
            "description": "D",
            "sku": "sku_auth_1",
            "price": "10.00",
            "stock": 1,
            "is_active": True,
        },
    )
    assert create_product.status_code == 201
    product_id = create_product.json()["id"]

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "password": "password123",
            "full_name": "Customer",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "customer@example.com", "password": "password123"},
    )
    token = login.json()["access_token"]

    patch = client.patch(
        f"/api/v1/products/{product_id}",
        headers=_bearer(token),
        json={"stock": 2},
    )
    assert patch.status_code == 403
    assert patch.json()["error"]["code"] == "forbidden"
    app.dependency_overrides.clear()


def test_patch_product_allowed_for_admin() -> None:
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        create_user(
            db,
            email="admin_patch@example.com",
            password="AdminPass1",
            full_name="Admin",
            role=UserRole.admin,
        )
    finally:
        db.close()

    client = TestClient(app)

    create_product = client.post(
        "/api/v1/products",
        json={
            "name": "Admin Item",
            "description": "D",
            "sku": "sku_auth_admin",
            "price": "10.00",
            "stock": 1,
            "is_active": True,
        },
    )
    assert create_product.status_code == 201
    product_id = create_product.json()["id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_patch@example.com", "password": "AdminPass1"},
    )
    token = login.json()["access_token"]

    patch = client.patch(
        f"/api/v1/products/{product_id}",
        headers=_bearer(token),
        json={"stock": 5},
    )
    assert patch.status_code == 200
    assert patch.json()["stock"] == 5
    app.dependency_overrides.clear()
