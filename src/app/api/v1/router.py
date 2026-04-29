from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.cart import router as cart_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.orders import router as orders_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.reviews import router as reviews_router
from app.api.v1.endpoints.wishlist import router as wishlist_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(cart_router)
api_router.include_router(orders_router)
api_router.include_router(products_router)
api_router.include_router(reviews_router)
api_router.include_router(rag_router)
api_router.include_router(wishlist_router)
