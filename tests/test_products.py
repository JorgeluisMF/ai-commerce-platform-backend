from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.product import Product
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


def test_create_product_success() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "name": "Keyboard Pro",
        "description": "Mechanical keyboard",
        "sku": "kb_pro_001",
        "price": "129.99",
        "stock": 15,
        "is_active": True,
    }

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Keyboard Pro"
    assert data["sku"] == "KB_PRO_001"
    assert data["price"] == "129.99"
    app.dependency_overrides.clear()


def test_create_product_with_image_urls() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "name": "Screen 4K",
        "description": "Monitor",
        "sku": "scr_4k_01",
        "price": "349.00",
        "stock": 4,
        "is_active": True,
        "images": [
            "https://cdn.example.com/p/a.jpg",
            "https://cdn.example.com/p/b.webp",
        ],
    }

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["images"] == [
        "https://cdn.example.com/p/a.jpg",
        "https://cdn.example.com/p/b.webp",
    ]
    app.dependency_overrides.clear()


def test_create_product_duplicate_sku_returns_409() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "name": "Mouse Pro",
        "description": "Wireless mouse",
        "sku": "mouse_001",
        "price": "59.90",
        "stock": 20,
        "is_active": True,
    }

    first_response = client.post("/api/v1/products", json=payload)
    second_response = client.post("/api/v1/products", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["message"] == "Product with this SKU already exists."
    app.dependency_overrides.clear()


def test_list_products_with_filter_and_pagination() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payloads = [
        {
            "name": "Laptop Air",
            "description": "Lightweight laptop",
            "sku": "laptop_air",
            "price": "999.00",
            "stock": 10,
            "is_active": True,
        },
        {
            "name": "Old Mouse",
            "description": "Discontinued mouse",
            "sku": "old_mouse",
            "price": "19.99",
            "stock": 0,
            "is_active": False,
        },
    ]
    for payload in payloads:
        response = client.post("/api/v1/products", json=payload)
        assert response.status_code == 201

    list_response = client.get("/api/v1/products?limit=1&offset=0&is_active=true")
    assert list_response.status_code == 200
    data = list_response.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["pages"] == 1
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "LAPTOP_AIR"
    app.dependency_overrides.clear()


def test_get_product_by_id_returns_404_when_not_found() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/api/v1/products/999")
    assert response.status_code == 404
    assert "was not found" in response.json()["error"]["message"]
    app.dependency_overrides.clear()


def test_patch_product_success_and_concurrency_conflict() -> None:
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        create_user(
            db,
            email="admin_products@test.com",
            password="AdminPass1",
            full_name="Admin",
            role=UserRole.admin,
        )
    finally:
        db.close()

    client = TestClient(app)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_products@test.com", "password": "AdminPass1"},
    )
    assert login_response.status_code == 200
    admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    create_payload = {
        "name": "Desk Lamp",
        "description": "Warm light lamp",
        "sku": "lamp_001",
        "price": "39.99",
        "stock": 50,
        "is_active": True,
    }
    create_response = client.post("/api/v1/products", json=create_payload)
    assert create_response.status_code == 201

    product = create_response.json()
    product_id = product["id"]
    expected_updated_at = product["updated_at"]

    patch_response = client.patch(
        f"/api/v1/products/{product_id}?expected_updated_at={expected_updated_at}",
        json={"price": "44.99", "stock": 40},
        headers=admin_headers,
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["price"] == "44.99"
    assert patched["stock"] == 40

    stale_patch_response = client.patch(
        f"/api/v1/products/{product_id}?expected_updated_at=2000-01-01T00:00:00Z",
        json={"stock": 35},
        headers=admin_headers,
    )
    assert stale_patch_response.status_code == 409
    assert "modified by another process" in stale_patch_response.json()["error"]["message"]
    app.dependency_overrides.clear()


def test_semantic_search_returns_503_when_disabled() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/api/v1/products/search/semantic?q=keyboard")
    assert response.status_code == 503
    assert "Semantic search is disabled" in response.json()["error"]["message"]
    app.dependency_overrides.clear()


def test_rag_ask_returns_local_pipeline_answer() -> None:
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "question": "Which product do you recommend for gaming?",
        "top_k": 3,
        "is_active": True,
    }
    response = client.post("/api/v1/rag/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == payload["question"]
    assert "No tengo suficiente evidencia" in data["answer"]
    assert isinstance(data["citations"], list)
    assert data["sources"] == data["citations"]
    assert data["low_confidence"] is True
    assert data["total_candidates"] == 0
    assert data["used_candidates"] == 0
    assert data["used_context_chars"] == 0
    app.dependency_overrides.clear()
