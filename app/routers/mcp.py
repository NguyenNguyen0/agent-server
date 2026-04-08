"""Router for MCP server CRUD and tool introspection."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import get_mcp_service
from app.middleware.auth import get_current_user
from app.models.mcp import MCPServerCreate, MCPServerResponse, MCPServerUpdate, MCPToolInfo
from app.services.mcp_service import MCPService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp/servers", tags=["mcp"])


@router.post("", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def register_server(
    payload: MCPServerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> MCPServerResponse:
    """Verify connectivity and register a new MCP server for the current user."""
    record = await service.register_server(
        user_id=current_user["id"],
        name=payload.name,
        url=str(payload.url),
        headers=payload.headers,
    )
    return MCPServerResponse(**record)


@router.get("", response_model=list[MCPServerResponse])
async def list_servers(
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> list[MCPServerResponse]:
    """List all MCP servers owned by the current user."""
    records = await service.list_servers(current_user["id"])
    return [MCPServerResponse(**r) for r in records]


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> MCPServerResponse:
    """Get details for a single MCP server owned by the current user."""
    record = await service.get_server(current_user["id"], server_id)
    return MCPServerResponse(**record)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> Response:
    """Delete an MCP server owned by the current user."""
    await service.delete_server(current_user["id"], server_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{server_id}/toggle", response_model=MCPServerResponse)
async def toggle_server(
    server_id: str,
    payload: MCPServerUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> MCPServerResponse:
    """Enable or disable an MCP server."""
    record = await service.toggle_server(current_user["id"], server_id, payload.is_active)
    return MCPServerResponse(**record)


@router.get("/{server_id}/tools", response_model=list[MCPToolInfo])
async def list_server_tools(
    server_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: MCPService = Depends(get_mcp_service),  # noqa: B008
) -> list[MCPToolInfo]:
    """Live-fetch the tool list from a registered MCP server."""
    raw_tools = await service.get_live_tools(current_user["id"], server_id)
    return [
        MCPToolInfo(
            name=t["name"],
            description=t.get("description", ""),
            input_schema=t.get("inputSchema", {}),
        )
        for t in raw_tools
    ]
