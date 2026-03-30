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


async def get_recipe_suggestions(
    ingredients: list[str],
    preferences: list[str] | None = None,
) -> list[Recipe]:
    ingredients_str = ", ".join(ingredients)

    user_content = f"Ich habe folgende Zutaten: {ingredients_str}. "
    if preferences:
        prefs_str = "\n".join(f"- {p}" for p in preferences)
        user_content += (
            f"\n\nFolgende Personen essen mit und haben diese Vorlieben/Einschränkungen:\n{prefs_str}\n\n"
            "Bitte berücksichtige die Vorlieben aller Personen bei den Rezeptvorschlägen. "
        )
    user_content += "Bitte erstelle eine Liste von 5 Rezepten. Nutze das return_recipes Tool."

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="Du bist ein Kochassistent. Antworte nur über das Tool.",
        messages=[{"role": "user", "content": user_content}],
        tools=[RECIPE_TOOL],
        tool_choice={"type": "tool", "name": "return_recipes"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return [Recipe(**r) for r in block.input["recipes"]]

    return []
