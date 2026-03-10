from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from apps.backend.agent.agent import app as agent_app


router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to the agent")
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation thread identifier. Omit to start a new session.",
    )
    reset: bool = Field(
        default=False,
        description="Force-reset the conversation state by discarding prior memory.",
    )


class AgentCard(BaseModel):
    card_name: Optional[str] = None
    card_company: Optional[str] = None
    annual_fee: Optional[int] = None
    min_performance: Optional[int] = None
    benefits_summary: Optional[str] = None


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    cards: list[AgentCard] = []
    analysis: Optional[dict[str, Any]] = None


def _pick_reply_from_events(events: list[dict[str, Any]]) -> Optional[str]:
    reply: Optional[str] = None

    def _as_text(content: Any) -> Optional[str]:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [part for part in content if isinstance(part, str)]
            if parts:
                return " ".join(parts)
        return None

    def _extract_from_messages(messages: Any) -> Optional[str]:
        if not messages or not isinstance(messages, list):
            return None
        found: Optional[str] = None
        for message in messages:
            if isinstance(message, AIMessage):
                found = _as_text(message.content) or found
            elif (
                isinstance(message, BaseMessage)
                and getattr(message, "type", None) == "ai"
            ):
                found = _as_text(message.content) or found
            elif isinstance(message, dict) and message.get("type") in (
                "ai",
                "assistant",
            ):
                content = _as_text(message.get("content"))
                found = content or found
        return found

    for event in events:
        # Events are shaped like {"node_name": {"messages": [...]}}. Scan all values.
        for value in event.values():
            if isinstance(value, dict) and "messages" in value:
                candidate = _extract_from_messages(value.get("messages"))
                reply = candidate or reply
    return reply


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    thread_id = None if payload.reset else payload.thread_id
    thread_id = thread_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    events: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {"messages": [HumanMessage(content=payload.message)]}

    if payload.reset or not payload.thread_id:
        inputs["retry_count"] = 0

    try:
        for event in agent_app.stream(inputs, config=config):
            events.append(event)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    reply = _pick_reply_from_events(events)

    state = agent_app.get_state(config).values
    analysis_obj = state.get("analysis")
    analysis = analysis_obj.model_dump() if analysis_obj else None

    raw_cards = []
    raw_data = state.get("last_raw_data")
    if isinstance(raw_data, str):
        try:
            parsed = json.loads(raw_data)
            if isinstance(parsed, list):
                raw_cards = parsed
        except json.JSONDecodeError:
            raw_cards = []

    cards: list[AgentCard] = []
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        cards.append(
            AgentCard(
                card_name=card.get("card_name"),
                card_company=card.get("card_company"),
                annual_fee=_safe_int(card.get("annual_fee")),
                min_performance=_safe_int(card.get("min_performance")),
                benefits_summary=card.get("benefits_summary"),
            )
        )

    return ChatResponse(
        thread_id=thread_id,
        reply=reply or "",
        cards=cards,
        analysis=analysis,
    )


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
