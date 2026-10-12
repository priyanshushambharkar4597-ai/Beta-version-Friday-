"""FastAPI Application Server for Friday - Thin, Observable REST/WebSocket API."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import PermissionGate, PermissionTier


app = FastAPI(
    title="Friday AI Assistant API",
    description="Thin, observable FastAPI backend for Friday's Cloud-Brain, Local-Body assistant.",
    version="0.1.0",
)

# Global Agent instance for the API server
_agent: Optional[FridayAgent] = None


def get_agent() -> FridayAgent:
    """Retrieve or instantiate singleton FridayAgent."""
    global _agent
    if _agent is None:
        provider = GeminiProvider()
        gate = PermissionGate()
        _agent = FridayAgent(gemini_provider=provider, permission_gate=gate)
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
    reply = agent.process(request.message)
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
    try:
        result = agent.execute_tool(request.tool_name, request.parameters)
        return {"status": "success", "result": result}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found.")
    except PermissionError as perm_err:
        raise HTTPException(status_code=403, detail=str(perm_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
