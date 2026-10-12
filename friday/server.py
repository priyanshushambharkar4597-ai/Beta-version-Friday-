"""FastAPI Application Server for Friday - Thin, Observable REST/WebSocket API with Jarvis HUD."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from friday.agent import FridayAgent
from friday.event_bus import EventType, SystemEvent, SystemEventBus
from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import PermissionGate, PermissionTier


app = FastAPI(
    title="Friday AI Assistant API",
    description="Thin, observable FastAPI backend for Friday's Cloud-Brain, Local-Body assistant.",
    version="0.2.0",
)

# Global instances
_agent: Optional[FridayAgent] = None
_event_bus: Optional[SystemEventBus] = None
_pending_security_requests: Dict[str, asyncio.Future] = {}


class ConnectionManager:
    """Manages active WebSocket connections for HUD clients."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def get_event_bus() -> SystemEventBus:
    """Retrieve or instantiate singleton SystemEventBus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = SystemEventBus()
    return _event_bus


def get_agent() -> FridayAgent:
    """Retrieve or instantiate singleton FridayAgent."""
    global _agent
    if _agent is None:
        provider = GeminiProvider()
        bus = get_event_bus()

        # Connect event bus to permission gate UI prompts
        def hud_confirm_callback(tool_name: str, description: str, params: Dict[str, Any]) -> bool:
            # First try terminal input if in interactive TTY
            import sys
            if sys.stdin.isatty():
                return PermissionGate._default_cli_confirm(tool_name, description, params)
            # Default auto-decline for security if no interactive input
            return False

        gate = PermissionGate(confirm_callback=hud_confirm_callback)
        _agent = FridayAgent(gemini_provider=provider, permission_gate=gate)

        # Wire event bus to agent activity
        def on_event(ev: SystemEvent):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.broadcast({
                        "type": "TELEMETRY_EVENT",
                        "event": {
                            "event_type": ev.event_type.value,
                            "payload": ev.payload,
                            "timestamp": ev.timestamp,
                        }
                    }))
            except Exception:
                pass

        for t in EventType:
            bus.subscribe(t, on_event)

    return _agent


class ChatRequest(BaseModel):
    message: str = Field(..., description="Message text from user")


class ChatResponse(BaseModel):
    response: str
    brain_model: str
    brain_online: bool


class RememberRequest(BaseModel):
    title: str
    content: str
    category: str = "general"
    tags: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)


class ToolExecutionRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


@app.get("/hud", response_class=HTMLResponse)
def get_hud() -> HTMLResponse:
    """Serve the Jarvis floating HUD HTML interface."""
    template_path = Path(__file__).parent / "ui" / "templates" / "hud.html"
    if template_path.exists():
        content = template_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse("<h1>HUD Template not found</h1>", status_code=404)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time HUD telemetry and voice state."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                # Handle client actions like security approvals
                if parsed.get("action") == "SECURITY_RESPONSE":
                    req_id = parsed.get("id")
                    approved = parsed.get("approved", False)
                    if req_id in _pending_security_requests:
                        _pending_security_requests[req_id].set_result(approved)
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Get system and hardware compliance status."""
    agent = get_agent()
    v_stats = agent.memory.graph_store.stats()
    return {
        "status": "online",
        "brain_model": agent.llm.model_name,
        "brain_online": agent.llm.is_configured(),
        "gpu_utilization_policy": "0% (Enforced)",
        "host_cpu": "Intel Core i5-12450H",
        "obsidian_notes_count": len(agent.memory.list_all_titles()),
        "knowledge_graph": v_stats,
        "registered_tools_count": len(agent.tools),
        "audit_records_count": len(agent.gate.audit_log),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Send prompt through Friday's agentic loop."""
    agent = get_agent()
    bus = get_event_bus()

    bus.publish(EventType.TEXT_INPUT, {"message": request.message}, source="api")
    reply = agent.process(request.message)
    bus.publish(EventType.RESPONSE_GENERATED, {"response": reply}, source="agent")

    return ChatResponse(
        response=reply,
        brain_model=agent.llm.model_name,
        brain_online=agent.llm.is_configured(),
    )


@app.post("/api/remember")
def remember(request: RememberRequest) -> Dict[str, Any]:
    """Store fact or note into physical Obsidian vault."""
    agent = get_agent()
    node = agent.memory.remember(
        title=request.title,
        content=request.content,
        category=request.category,
        tags=request.tags,
        links=request.links,
    )
    bus = get_event_bus()
    bus.publish(EventType.MEMORY_STORED, {"title": node.title, "path": node.file_path})
    return {
        "status": "saved",
        "id": node.id,
        "title": node.title,
        "file_path": node.file_path,
        "tags": node.tags,
        "links": node.links,
    }


@app.get("/api/vault")
def list_vault() -> Dict[str, Any]:
    """List notes stored in the physical Obsidian vault."""
    agent = get_agent()
    titles = agent.memory.list_all_titles()
    v_stats = agent.memory.graph_store.stats()
    return {
        "vault_dir": str(agent.memory.vault.vault_dir),
        "total_notes": len(titles),
        "notes": titles,
        "graph_nodes": v_stats["total_nodes"],
        "graph_edges": v_stats["total_edges"],
    }


@app.get("/api/recall")
def recall(q: str, top_k: int = 3, max_hops: int = 2) -> Dict[str, Any]:
    """Query memory engine using vector search + 2-hop graph expansion."""
    agent = get_agent()
    return agent.memory.recall(query=q, top_k=top_k, max_hops=max_hops)


@app.get("/api/tools")
def list_tools() -> List[Dict[str, Any]]:
    """List all available tools and their safety tiers."""
    agent = get_agent()
    return agent.list_tools()


@app.post("/api/tools/execute")
def execute_tool(request: ToolExecutionRequest) -> Dict[str, Any]:
    """Execute a registered tool through the security permission gate."""
    agent = get_agent()
    bus = get_event_bus()
    bus.publish(EventType.TOOL_ACTION, {"tool": request.tool_name, "params": request.parameters})

    try:
        result = agent.execute_tool(request.tool_name, request.parameters)
        bus.publish(EventType.TOOL_OBSERVATION, {"tool": request.tool_name, "result": result})
        return {"status": "success", "result": result}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found.")
    except PermissionError as perm_err:
        raise HTTPException(status_code=403, detail=str(perm_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
