from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_recipe_image(recipe_name: str) -> str | None:
    response = await openai_client.images.generate(
        model="dall-e-3",
        prompt=(
            f"Ein realistisches Bild von '{recipe_name}', ein leckeres Gericht. "
            "Hochwertige Food-Fotografie, ästhetisch angerichtet."
        ),
        n=1,
        size="1024x1024",
    )
    return response.data[0].url
