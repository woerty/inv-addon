from __future__ import annotations

from pydantic import BaseModel


class Recipe(BaseModel):
    name: str
    short_description: str
    ingredients: list[str]
    instructions: str


class RecipeListResponse(BaseModel):
    recipes: list[Recipe]


class RecipeImageRequest(BaseModel):
    name: str
    generate_image: bool = True


class RecipeImageResponse(BaseModel):
    image_url: str | None = None
