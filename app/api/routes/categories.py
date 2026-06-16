from fastapi import APIRouter

from app.api.deps import category_service
from app.models.schemas import Category

router = APIRouter()


@router.get("/categories", response_model=list[Category])
def get_categories() -> list[Category]:
    return category_service.get_categories()
