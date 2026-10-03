from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings

# Created on first use: openai>=3 raises at construction when the key is
# empty, which at import time took the whole backend down with it.
openai_client: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    global openai_client
    if openai_client is None:
        openai_client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return openai_client


async def generate_recipe_image(recipe_name: str) -> str | None:
    response = await _client().images.generate(
        model="dall-e-3",
        prompt=(
            f"Ein realistisches Bild von '{recipe_name}', ein leckeres Gericht. "
            "Hochwertige Food-Fotografie, ästhetisch angerichtet."
        ),
        n=1,
        size="1024x1024",
    )
    return response.data[0].url
