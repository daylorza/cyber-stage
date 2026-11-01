"""Session-only Live-In Guide. Only Spark is used; tools read prepared listing data."""
import json
import os
import re
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context
from pydantic import BaseModel, Field, field_validator

import db

router = APIRouter(prefix="/api")
_memory = InMemorySaver()
_sessions: dict[tuple[str, str], dict[str, Any]] = {}
_lock = threading.Lock()
STYLE_LABELS = {"modern-luxury": "Modern luxury", "coastal": "Coastal", "minimal": "Minimal", "2142": "Cyberpunk"}
STYLE_ALIASES = {"modern": "modern-luxury", "modern luxury": "modern-luxury", "coastal": "coastal",
                 "minimal": "minimal", "cyberpunk": "2142", "cyberpunk 2142": "2142", "2142": "2142"}
SYSTEM = """You are the Live-In Guide for this residence only. Use tools for facts and actions.
Answer only from listing facts and stored observations; cite fact or observation ids for claims.
Demo comps are demo data, not a live MLS feed. Cyberpunk is a concept, AI-imagined,
not a verified depiction. A deposit is simulated and no payment is taken. Do not provide
investment advice or a best-home verdict; offer facts and staged options and say a broker decides.
Do not claim an action succeeded unless its tool says so. Do not claim styles are
available unless get_room confirms them in available_styles. Before a style switch or
listing style options, call get_room. Use display labels when speaking: Cyberpunk,
Modern luxury, Coastal, Minimal. Cyberpunk corresponds to style ID 2142; Modern
means Modern luxury. Call switch_style with the requested name or ID."""


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    room_id: str | None = None
    style_id: str | None = None

    @field_validator("thread_id", "message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


def _model():
    return ChatOpenAI(model="muse-spark-1.3", base_url="https://api.meta.ai/v1",
                      api_key=os.environ.get("META_API_KEY"), timeout=45, max_retries=0)


def _cited_evidence(text: str, listing: dict) -> list[str]:
    facts = (listing.get("published") or {}).get("facts") or listing.get("facts") or {}
    valid = {f"fact:{key}" for key, value in facts.items() if value is not None}
    if (listing.get("published") or {}).get("title"):
        valid.add("fact:title")
    valid.update(o["id"] for frame in listing.get("frames", [])
                 for o in (frame.get("wonder") or {}).get("observations", []) if o.get("id"))
    return list(dict.fromkeys(x for x in re.findall(r"fact:[\w-]+|o_[\w-]+", text) if x in valid))


def _tools(listing: dict, session: dict, result: dict):
    rooms = (listing.get("live") or {}).get("rooms") or []

    def current():
        return next((r for r in rooms if r.get("id") == session.get("room_id")), rooms[0] if rooms else None)

    def record(name, data):
        result["actions_taken"].append(name)
        return json.dumps(data)

    def available_styles(room):
        styles = (room or {}).get("styles", {})
        return [label for key, label in STYLE_LABELS.items()
                if (styles.get(key) or {}).get("available") and styles[key].get("image")]

    @tool
    def get_listing_facts() -> str:
        """Get the residence's supplied facts with evidence identifiers."""
        facts = (listing.get("published") or {}).get("facts") or listing.get("facts") or {}
        data = {f"fact:{k}": v for k, v in facts.items() if k in {"beds", "baths", "sqft", "price", "currency", "city", "address"} and v is not None}
        title = (listing.get("published") or {}).get("title")
        if title:
            data["fact:title"] = title
        result["evidence"].extend(data)
        return record("get_listing_facts", data)

    @tool
    def get_room(room_id: str = "") -> str:
        """Get a room and its stored observations. Omit room_id for the current room."""
        room = next((r for r in rooms if r.get("id") == room_id), None) if room_id else current()
        if not room:
            return record("get_room", {"error": "Room not found"})
        source = next((r for r in listing.get("rooms", []) if r.get("id") == room["id"]), {})
        frame_ids = set(source.get("frames") or []) | {source.get("source_frame")}
        observations = [o for f in listing.get("frames", []) if f.get("id") in frame_ids for o in (f.get("wonder") or {}).get("observations", [])]
        result["evidence"].extend(o["id"] for o in observations if o.get("id"))
        style = session.get("style", "modern-luxury")
        return record("get_room", {"id": room["id"], "type": room.get("type"), "observations": observations, "style": STYLE_LABELS.get(style, style), "available_styles": available_styles(room), "staged_image": (room.get("styles", {}).get(style) or {}).get("image")})

    @tool
    def explain_comps() -> str:
        """Get the residence's demo comparable properties, not live MLS data."""
        return record("explain_comps", {"label": "Demo data, not a live MLS feed", "comps": listing.get("comps")})

    @tool
    def switch_style(style_id: str) -> str:
        """Switch the current room to modern-luxury, coastal, minimal, or cyberpunk-2142."""
        style = STYLE_ALIASES.get(re.sub(r"[\s-]+", " ", style_id.strip().lower()))
        room = current()
        entry = (room.get("styles", {}).get(style) or {}) if room else {}
        if not style or not entry.get("available") or not entry.get("image"):
            return record("switch_style", {"error": entry.get("error") or "Style unavailable for this room", "available_styles": available_styles(room)})
        session["style"] = style
        result["staged_image_url"] = "/api/media/" + entry["image"].lstrip("/")
        data = {"room_id": room["id"], "style": STYLE_LABELS[style], "style_id": style, "staged_image_url": result["staged_image_url"]}
        if style == "2142":
            data["disclaimer"] = "Cyberpunk concept · AI-imagined, not a verified depiction of the property"
        return record("switch_style", data)

    @tool
    def next_room() -> str:
        """Move to the next prepared room in walkthrough order."""
        room = current()
        if not room:
            return record("next_room", {"error": "No prepared room available"})
        index = rooms.index(room)
        if index + 1 >= len(rooms):
            return record("next_room", {"error": "Already in the last room"})
        room = rooms[index + 1]
        session["room_id"] = room["id"]
        result["room_id"] = room["id"]
        entry = room.get("styles", {}).get(session.get("style", "modern-luxury")) or {}
        if entry.get("available") and entry.get("image"):
            result["staged_image_url"] = "/api/media/" + entry["image"].lstrip("/")
        return record("next_room", {"room_id": room["id"], "staged_image_url": result["staged_image_url"]})

    @tool
    def simulated_deposit() -> str:
        """Create a mock deposit confirmation; no money is taken."""
        result["deposit"] = {"simulated": True, "payment_taken": False, "mock_tx": db.new_id("mock")}
        return record("simulated_deposit", result["deposit"])

    return [get_listing_facts, get_room, explain_comps, switch_style, next_room, simulated_deposit]


@router.post("/listings/{listing_id}/guide/chat")
def chat(listing_id: str, body: ChatRequest) -> dict:
    listing = db.get_listing(listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found.")
    if listing.get("status") != "published" or (listing.get("live") or {}).get("status") != "ready":
        raise HTTPException(409, "A published, prepared residence is required.")
    result = {"text": "", "emotion": "warm", "actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None, "room_id": None}
    # ponytail: a process-wide lock serializes demo sessions; use per-session locks if traffic grows.
    with _lock:
        key = (listing_id, body.thread_id)
        session = _sessions.setdefault(key, {"turns": 0})
        rooms = (listing.get("live") or {}).get("rooms") or []
        if body.room_id and any(room.get("id") == body.room_id for room in rooms):
            session["room_id"] = body.room_id
        if body.style_id in (*STYLE_LABELS, "original"):
            session["style"] = body.style_id
        if session["turns"] >= 12:
            result["text"] = "This demo session has reached its 12-turn limit. Please start a new session."
            return result
        session["turns"] += 1
        try:
            agent = create_agent(_model(), _tools(listing, session, result), system_prompt=SYSTEM, checkpointer=_memory)
            with tracing_context(enabled=False):
                output = agent.invoke({"messages": [{"role": "user", "content": body.message}]},
                                      {"configurable": {"thread_id": json.dumps(key)}, "recursion_limit": 16})
            result["text"] = str(output["messages"][-1].content)
        except Exception:
            raise HTTPException(503, "The guide is temporarily unavailable. Please try again.") from None
    if result["deposit"]:
        result["text"] += "\nSimulated deposit — no payment taken."
    if session.get("style") == "2142" and "cyberpunk" in result["text"].lower():
        result["text"] += "\nCyberpunk concept · AI-imagined, not a verified depiction of the property."
    result["emotion"] = "excited" if result["deposit"] or result["staged_image_url"] else "calm" if result["evidence"] else "warm"
    result["evidence"] = _cited_evidence(result["text"], listing)
    return result
