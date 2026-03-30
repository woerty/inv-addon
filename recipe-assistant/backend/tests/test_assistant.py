from unittest.mock import AsyncMock, MagicMock, patch


async def test_chat_service_returns_response():
    from app.services.ai_chat import get_chat_response

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hier ist ein Rezept für Pfannkuchen.")]

    with patch("app.services.ai_chat.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await get_chat_response(
            messages=[{"role": "user", "content": "Was kann ich mit Mehl machen?"}],
            system_prompt="Du bist ein Kochassistent.",
        )

    assert "Pfannkuchen" in result


async def test_recipe_service_returns_recipes():
    from app.services.ai_recipes import get_recipe_suggestions

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "recipes": [
                    {
                        "name": "Pfannkuchen",
                        "short_description": "Einfache Pfannkuchen",
                        "ingredients": ["Mehl", "Milch", "Eier"],
                        "instructions": "Alles verrühren und braten.",
                    }
                ]
            },
        )
    ]

    with patch("app.services.ai_recipes.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await get_recipe_suggestions(["Mehl", "Milch", "Eier"])

    assert len(result) == 1
    assert result[0].name == "Pfannkuchen"


async def test_image_service_returns_url():
    from app.services.ai_images import generate_recipe_image

    mock_image = MagicMock()
    mock_image.data = [MagicMock(url="https://example.com/image.png")]

    with patch("app.services.ai_images.openai_client") as mock_client:
        mock_client.images.generate = AsyncMock(return_value=mock_image)
        result = await generate_recipe_image("Pfannkuchen")

    assert result == "https://example.com/image.png"
