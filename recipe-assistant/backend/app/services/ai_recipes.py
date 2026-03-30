from __future__ import annotations

import anthropic

from app.config import get_settings
from app.schemas.recipe import Recipe

settings = get_settings()
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

RECIPE_TOOL = {
    "name": "return_recipes",
    "description": "Return a list of recipe suggestions based on available ingredients.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recipes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name des Rezepts"},
                        "short_description": {"type": "string", "description": "Kurzbeschreibung"},
                        "ingredients": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste der Zutaten mit Mengenangaben",
                        },
                        "instructions": {"type": "string", "description": "Zubereitungsanleitung als Markdown"},
                    },
                    "required": ["name", "short_description", "ingredients", "instructions"],
                },
                "description": "Liste von 5 Rezeptvorschlägen",
            }
        },
        "required": ["recipes"],
    },
}


async def get_recipe_suggestions(ingredients: list[str]) -> list[Recipe]:
    ingredients_str = ", ".join(ingredients)

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="Du bist ein Kochassistent. Antworte nur über das Tool.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Ich habe folgende Zutaten: {ingredients_str}. "
                    "Bitte erstelle eine Liste von 5 Rezepten mit diesen Zutaten. "
                    "Nutze das return_recipes Tool."
                ),
            }
        ],
        tools=[RECIPE_TOOL],
        tool_choice={"type": "tool", "name": "return_recipes"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return [Recipe(**r) for r in block.input["recipes"]]

    return []
