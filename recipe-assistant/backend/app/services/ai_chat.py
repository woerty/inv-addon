from __future__ import annotations

import anthropic

from app.config import get_settings

settings = get_settings()
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

DEFAULT_SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Kochassistent. Du antwortest auf Deutsch und hilfst "
    "beim Kochen, bei Rezepten und bei Fragen rund um Lebensmittel."
)


async def get_chat_response(
    messages: list[dict[str, str]],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> str:
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text
