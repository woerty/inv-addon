from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import ChatMessage
from app.models.inventory import InventoryItem
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse, ChatRequest, ChatResponse
from app.schemas.recipe import RecipeImageRequest, RecipeImageResponse, RecipeListResponse
from app.services.ai_chat import get_chat_response
from app.services.ai_images import generate_recipe_image
from app.services.ai_recipes import get_recipe_suggestions

router = APIRouter()


@router.get("/recipes", response_model=RecipeListResponse)
async def recipe_suggestions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InventoryItem.name).where(InventoryItem.quantity > 0)
    )
    ingredients = [row[0] for row in result.all()]

    if not ingredients:
        raise HTTPException(status_code=400, detail="Keine Lebensmittel im Inventar gefunden.")

    recipes = await get_recipe_suggestions(ingredients)
    return RecipeListResponse(recipes=recipes)


@router.post("/recipe-image", response_model=RecipeImageResponse)
async def recipe_image(req: RecipeImageRequest):
    if not req.generate_image:
        return RecipeImageResponse(image_url=None)

    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Kein Rezeptname angegeben.")

    url = await generate_recipe_image(req.name)
    return RecipeImageResponse(image_url=url)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Leere Nachricht kann nicht verarbeitet werden.")

    session_id = req.session_id or str(uuid.uuid4())

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
    )
    history_rows = result.scalars().all()
    messages: list[dict[str, str]] = [{"role": m.role, "content": m.content} for m in history_rows]

    system_suffix = ""
    if not messages and req.use_ingredients:
        inv_result = await db.execute(
            select(InventoryItem.name).where(InventoryItem.quantity > 0)
        )
        ingredients = [row[0] for row in inv_result.all()]
        if ingredients:
            system_suffix = f"\n\nDer Nutzer hat folgende Zutaten im Haushalt: {', '.join(ingredients)}."

    messages.append({"role": "user", "content": req.message})

    system_prompt = "Du bist ein hilfreicher Kochassistent. Du antwortest auf Deutsch."
    if system_suffix:
        system_prompt += system_suffix

    ai_response = await get_chat_response(messages=messages, system_prompt=system_prompt)

    db.add(ChatMessage(session_id=session_id, role="user", content=req.message))
    db.add(ChatMessage(session_id=session_id, role="assistant", content=ai_response))
    await db.commit()

    return ChatResponse(response=ai_response, session_id=session_id)


@router.post("/chat/clear/{session_id}")
async def clear_chat(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    messages = result.scalars().all()
    for msg in messages:
        await db.delete(msg)
    await db.commit()
    return {"message": "Chatverlauf wurde gelöscht."}


@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
    )
    messages = result.scalars().all()
    return ChatHistoryResponse(
        messages=[ChatMessageResponse.model_validate(m) for m in messages],
        session_id=session_id,
    )
