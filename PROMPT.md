# prompt.md — Implementation Roadmap

> Tài liệu này dành cho **agent coding** (Cursor, Claude, Copilot, ...).
> Đọc `agents.md` trước để nắm convention. Sau đó thực hiện các Phase dưới đây **theo thứ tự**.
> Mỗi Phase phải có test pass trước khi chuyển sang Phase tiếp theo (TDD).

---

## Tổng quan hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                        agent-server                          │
│                                                             │
│  User ──► Auth (Supabase JWT)                               │
│             │                                               │
│             ▼                                               │
│  Session Manager  ──► Supabase (sessions + messages)        │
│             │                                               │
│             ▼                                               │
│  Chat Agent (LangGraph)                                     │
│    ├── Context: uploaded files (pgvector)                   │
│    ├── Tools: MCP over HTTP (per-user config)               │
│    └── Tools: Web Search (built-in, optional)               │
│             │                                               │
│             ▼                                               │
│  Groq LLM  ◄────────────────────────────────────────────── │
└─────────────────────────────────────────────────────────────┘
```

---

## Supabase Schema (chạy trước khi bắt đầu code)

```sql
-- Enable pgvector
create extension if not exists vector;

-- Sessions
create table sessions (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references auth.users(id) on delete cascade not null,
  title        text not null default 'New Chat',
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

-- Messages
create table messages (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid references sessions(id) on delete cascade not null,
  role         text check (role in ('user', 'assistant', 'tool')) not null,
  content      text not null,
  tool_calls   jsonb,
  created_at   timestamptz default now()
);

-- Uploaded files metadata
create table files (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid references sessions(id) on delete cascade not null,
  user_id      uuid references auth.users(id) on delete cascade not null,
  filename     text not null,
  mime_type    text not null,
  size_bytes   bigint not null,
  storage_path text not null,       -- Supabase Storage path
  created_at   timestamptz default now()
);

-- Document chunks (RAG)
create table document_chunks (
  id           uuid primary key default gen_random_uuid(),
  file_id      uuid references files(id) on delete cascade not null,
  session_id   uuid references sessions(id) on delete cascade not null,
  user_id      uuid references auth.users(id) on delete cascade not null,
  content      text not null,
  chunk_index  int not null,
  embedding    vector(1536),
  metadata     jsonb default '{}',
  created_at   timestamptz default now()
);

-- MCP server configs per user
create table mcp_servers (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references auth.users(id) on delete cascade not null,
  name         text not null,
  url          text not null,        -- HTTP/SSE endpoint
  description  text,
  headers      jsonb default '{}',   -- auth headers nếu cần
  is_active    boolean default true,
  created_at   timestamptz default now(),
  unique (user_id, name)
);

-- Vector search function
create or replace function match_chunks(
  query_embedding  vector(1536),
  session_id_filter uuid,
  match_threshold  float default 0.7,
  match_count      int   default 5
)
returns table (
  id         uuid,
  content    text,
  metadata   jsonb,
  similarity float
)
language sql stable as $$
  select
    id, content, metadata,
    1 - (embedding <=> query_embedding) as similarity
  from document_chunks
  where
    session_id = session_id_filter
    and 1 - (embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
$$;

-- RLS Policies
alter table sessions        enable row level security;
alter table messages        enable row level security;
alter table files           enable row level security;
alter table document_chunks enable row level security;
alter table mcp_servers     enable row level security;

create policy "users own sessions"        on sessions        for all using (auth.uid() = user_id);
create policy "users own messages"        on messages        for all using (session_id in (select id from sessions where user_id = auth.uid()));
create policy "users own files"           on files           for all using (auth.uid() = user_id);
create policy "users own chunks"          on document_chunks for all using (auth.uid() = user_id);
create policy "users own mcp_servers"     on mcp_servers     for all using (auth.uid() = user_id);
```

---

## Phase 1 — Foundation (Skeleton & Auth)

> **Mục tiêu:** Dự án chạy được, auth hoạt động, CI xanh.
> **Độ khó:** ⭐☆☆☆☆

### 1.1 Khởi tạo dự án

```bash
uv init agent-server
cd agent-server
uv python pin 3.12

uv add fastapi "uvicorn[standard]" pydantic-settings supabase python-multipart
uv add langgraph langchain "langchain-groq" langserve
uv add --dev pytest pytest-asyncio pytest-cov respx ruff mypy
```

Tạo cấu trúc thư mục theo `agents.md § 2`. Tạo file rỗng `__init__.py` cho tất cả packages.

### 1.2 Config

**File:** `app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Groq
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_file_size_mb: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 200


settings = Settings()
```

**File:** `.env.example`

```bash
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
APP_ENV=development
```

### 1.3 FastAPI Entry Point

**File:** `app/main.py`

- Tạo `FastAPI` app với title, version
- Thêm `CORSMiddleware` dùng `settings.cors_origins`
- Include router `/health` trả `{"status": "ok"}`
- Global exception handlers cho custom exceptions (xem `agents.md § 10`)

### 1.4 Auth Dependency

**File:** `app/middleware/auth.py`

- Implement `get_current_user(credentials, db)` như `agents.md § 8.2`
- Dùng `db.auth.get_user(token)` để validate Supabase JWT
- Raise `HTTPException(401)` nếu invalid

### 1.5 Tests cho Phase 1

```
tests/unit/test_config.py          — settings load từ env đúng
tests/unit/middleware/test_auth.py — valid token → user dict, invalid → 401
tests/integration/test_health.py   — GET /health → 200 {"status": "ok"}
```

**Definition of Done Phase 1:**
- [ ] `make test` pass 100%
- [ ] `make lint` không có lỗi
- [ ] `GET /health` trả `200`
- [ ] Token hợp lệ qua `get_current_user`, token sai raise `401`

---

## Phase 2 — Session Management

> **Mục tiêu:** User tạo/đọc/xoá chat sessions, xem lịch sử messages.
> **Độ khó:** ⭐⭐☆☆☆

### 2.1 Pydantic Models

**File:** `app/models/session.py`

```python
from pydantic import BaseModel
from datetime import datetime


class SessionCreate(BaseModel):
    title: str = "New Chat"


class SessionResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionList(BaseModel):
    sessions: list[SessionResponse]
    total: int
```

**File:** `app/models/message.py`

```python
from pydantic import BaseModel
from datetime import datetime


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: dict | None = None
    created_at: datetime


class MessageHistory(BaseModel):
    messages: list[MessageResponse]
```

### 2.2 Repositories

**File:** `app/repositories/session_repo.py`

Kế thừa `BaseRepository[dict]`. Thêm methods:
- `find_by_user(user_id: str) -> list[dict]`
- `find_by_user_and_id(user_id: str, session_id: str) -> dict | None`
  - Kiểm tra ownership — không để user đọc session của người khác

**File:** `app/repositories/message_repo.py`

Kế thừa `BaseRepository[dict]`. Thêm methods:
- `find_by_session(session_id: str) -> list[dict]` — sorted by `created_at ASC`
- `create_message(session_id: str, role: str, content: str, tool_calls: dict | None = None) -> dict`

### 2.3 Services

**File:** `app/services/session_service.py`

```python
class SessionService:
    def __init__(self, session_repo: SessionRepository, message_repo: MessageRepository) -> None: ...

    async def create_session(self, user_id: str, title: str) -> dict: ...
    async def list_sessions(self, user_id: str) -> list[dict]: ...
    async def get_session(self, user_id: str, session_id: str) -> dict: ...
        # Raise SessionNotFoundError nếu không tìm thấy hoặc không phải owner
    async def delete_session(self, user_id: str, session_id: str) -> None: ...
    async def get_history(self, user_id: str, session_id: str) -> list[dict]: ...
```

### 2.4 Router

**File:** `app/routers/sessions.py`

```
POST   /sessions                    → tạo session mới
GET    /sessions                    → list sessions của current user
GET    /sessions/{session_id}       → chi tiết session
DELETE /sessions/{session_id}       → xoá session
GET    /sessions/{session_id}/messages → lịch sử messages
```

Tất cả routes đều require `current_user = Depends(get_current_user)`.

### 2.5 Tests cho Phase 2

```
tests/unit/repositories/test_session_repo.py
tests/unit/repositories/test_message_repo.py
tests/unit/services/test_session_service.py
tests/integration/test_sessions_api.py
```

**Scenarios bắt buộc:**
- User A không thể xem session của User B → `404`
- Delete session → cascade xoá messages
- List sessions chỉ trả sessions của user hiện tại

**Definition of Done Phase 2:**
- [ ] CRUD sessions hoạt động đúng
- [ ] Ownership check nghiêm ngặt
- [ ] Messages sorted đúng thứ tự
- [ ] Coverage ≥ 80% cho phase này

---

## Phase 3 — Basic Chat (Conversational Chatbot)

> **Mục tiêu:** User chat trong session, lịch sử được lưu, LLM trả lời có context.
> **Độ khó:** ⭐⭐☆☆☆

### 3.1 LangGraph Chatbot Graph

**File:** `app/graphs/nodes/llm_node.py`

```python
from langchain_groq import ChatGroq
from app.graphs.chatbot_graph import ChatbotState


async def llm_node(state: ChatbotState, llm: ChatGroq) -> dict:
    """Gọi LLM với toàn bộ message history."""
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}
```

**File:** `app/graphs/chatbot_graph.py`

```python
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from functools import partial


class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_chatbot_graph(llm) -> ...:
    graph = StateGraph(ChatbotState)
    graph.add_node("llm", partial(llm_node, llm=llm))
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)
    return graph.compile(checkpointer=MemorySaver())
```

### 3.2 Chat Agent

**File:** `app/agents/chatbot_agent.py`

Implement `ChatbotAgent(BaseAgent)` như `agents.md § 6.1`.

Lưu ý: `MemorySaver` chỉ lưu in-memory. Sau mỗi `ainvoke`, service phải **tự lưu** message vào Supabase qua `MessageRepository`.

### 3.3 Chat Service

**File:** `app/services/chat_service.py`

```python
class ChatService:
    async def chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> str:
        """
        1. Verify session ownership
        2. Load message history từ Supabase
        3. Invoke chatbot agent (inject history vào state)
        4. Lưu user message + assistant response vào Supabase
        5. Return assistant content
        """

    async def stream_chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> AsyncIterator[str]:
        """Stream version — yield từng token, lưu full response sau khi xong."""
```

### 3.4 Pydantic Models

**File:** `app/models/chat.py`

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8192)
    agent_type: str = Field(default="chatbot", pattern="^(chatbot|rag|tool)$")
    use_web_search: bool = False          # Phase 6
    mcp_server_ids: list[str] = []       # Phase 5


class ChatResponse(BaseModel):
    content: str
    session_id: str
    message_id: str
```

### 3.5 Router

**File:** `app/routers/chat.py`

```
POST /sessions/{session_id}/chat         → invoke, trả ChatResponse
POST /sessions/{session_id}/chat/stream  → SSE streaming
```

**SSE format:**

```
data: {"token": "Hello"}\n\n
data: {"token": " world"}\n\n
data: [DONE]\n\n
```

### 3.6 Tests cho Phase 3

```
tests/unit/graphs/test_chatbot_graph.py      — graph invoke với mock LLM
tests/unit/agents/test_chatbot_agent.py      — ainvoke/astream với mock graph
tests/unit/services/test_chat_service.py     — chat lưu messages, verify ownership
tests/integration/test_chat_api.py           — POST /sessions/{id}/chat end-to-end
```

**Definition of Done Phase 3:**
- [ ] Chat trả lời đúng
- [ ] History được load và inject vào LLM context
- [ ] Messages được lưu vào Supabase sau mỗi turn
- [ ] Streaming endpoint hoạt động và emit đúng SSE format

---

## Phase 4 — File Upload & RAG Context

> **Mục tiêu:** User upload file vào session, agent tự động dùng nội dung file khi chat.
> **Độ khó:** ⭐⭐⭐☆☆

### 4.1 Supported File Types

| Loại | Xử lý |
|---|---|
| `.txt`, `.md` | Đọc trực tiếp |
| `.pdf` | Dùng `pypdf` extract text |
| `.docx` | Dùng `python-docx` extract text |
| `.csv`, `.json` | Đọc raw text |

```bash
uv add pypdf python-docx langchain-text-splitters langchain-community
```

### 4.2 File Processing Pipeline

**File:** `app/services/file_service.py`

```python
class FileService:
    async def upload_file(
        self,
        user_id: str,
        session_id: str,
        file: UploadFile,
    ) -> dict:
        """
        1. Validate: size ≤ MAX_FILE_SIZE_MB, mime_type được hỗ trợ
        2. Upload raw file lên Supabase Storage (bucket: "uploads")
           path: {user_id}/{session_id}/{filename}
        3. Lưu metadata vào bảng files
        4. Extract text từ file (theo mime_type)
        5. Chunk text (RecursiveCharacterTextSplitter)
        6. Embed từng chunk (Groq không có embedding → dùng langchain-community HuggingFaceEmbeddings hoặc OpenAI)
        7. Lưu chunks + embeddings vào bảng document_chunks
        8. Return file metadata
        """

    async def delete_file(self, user_id: str, file_id: str) -> None:
        """Xoá file khỏi Storage và cascade xoá chunks."""

    async def list_files(self, user_id: str, session_id: str) -> list[dict]:
        """List files của session."""
```

> **Lưu ý embedding model:** Groq không cung cấp embedding API.
> Dùng `langchain_community.embeddings.HuggingFaceEmbeddings` với model `"sentence-transformers/all-MiniLM-L6-v2"` (free, local, 384 dims).
> Hoặc thêm `OPENAI_API_KEY` và dùng `OpenAIEmbeddings` (1536 dims — khớp schema SQL trên).
> **Quyết định:** Mặc định dùng HuggingFace local, update schema `embedding vector(384)` cho phù hợp.

**File:** `app/services/vector_service.py`

```python
class VectorService:
    async def similarity_search(
        self,
        query: str,
        session_id: str,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict]:
        """Embed query rồi gọi Supabase RPC match_chunks."""

    async def has_context(self, session_id: str) -> bool:
        """Kiểm tra session có document chunks không."""
```

### 4.3 RAG Graph

**File:** `app/graphs/nodes/retriever_node.py`

```python
async def retriever_node(state: RagState, vector_service: VectorService) -> dict:
    """Tìm kiếm chunks liên quan đến query cuối."""
    last_human = [m for m in state["messages"] if m.type == "human"][-1]
    chunks = await vector_service.similarity_search(
        query=last_human.content,
        session_id=state["session_id"],
    )
    context = [c["content"] for c in chunks]
    return {"context": context}
```

**File:** `app/graphs/rag_graph.py`

```python
class RagState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    context: list[str]      # populated by retriever_node
```

Graph flow: `retrieve` → `generate` → `END`

**File:** `app/prompts/rag.py`

```python
RAG_SYSTEM = """\
You are a helpful assistant. The user has uploaded files to this chat session.

When relevant, use the following context extracted from their files to answer:

<context>
{context}
</context>

If the context doesn't contain enough information, answer from your general knowledge \
but mention that the uploaded files didn't cover this topic.
"""
```

### 4.4 Smart Agent Router

**File:** `app/services/chat_service.py` — cập nhật

```python
async def chat(self, user_id, session_id, message, request: ChatRequest) -> str:
    """
    Auto-select agent type:
    - Nếu session có uploaded files → dùng RagAgent
    - Ngược lại → dùng ChatbotAgent
    (user cũng có thể force agent_type qua request.agent_type)
    """
    has_files = await self.vector_service.has_context(session_id)
    agent = self._select_agent(request.agent_type, has_files)
    ...
```

### 4.5 Router

**File:** `app/routers/files.py`

```
POST   /sessions/{session_id}/files              → upload file (multipart/form-data)
GET    /sessions/{session_id}/files              → list files
DELETE /sessions/{session_id}/files/{file_id}   → xoá file + chunks
```

### 4.6 Tests cho Phase 4

```
tests/unit/services/test_file_service.py
  — validate file size, mime type
  — extract text từ pdf/txt/docx (dùng fixture files thật trong tests/fixtures/)
  — chunk và embed đúng số lượng
  — upload fail → không lưu DB

tests/unit/services/test_vector_service.py
  — similarity_search gọi supabase RPC đúng params
  — has_context trả True/False đúng

tests/unit/graphs/test_rag_graph.py
  — retriever_node inject context vào state
  — generate_node dùng context trong prompt

tests/integration/test_files_api.py
  — upload txt → 200, chunks được tạo
  — chat sau upload → response có dùng nội dung file
```

**Test fixtures:**

```
tests/fixtures/
├── sample.txt       # plain text ngắn
├── sample.pdf       # PDF 1 trang
└── sample.docx      # Word doc đơn giản
```

**Definition of Done Phase 4:**
- [ ] Upload PDF/TXT/DOCX hoạt động
- [ ] Chunks được embed và lưu vào Supabase pgvector
- [ ] Chat trong session có file → agent tự dùng RAG
- [ ] Delete file → xoá sạch chunks
- [ ] File > MAX_FILE_SIZE_MB → `413`

---

## Phase 5 — MCP Server Management

> **Mục tiêu:** User thêm MCP server qua HTTP URL, agent dùng tools từ MCP khi chat.
> **Độ khó:** ⭐⭐⭐⭐☆

### 5.1 Pydantic Models

**File:** `app/models/mcp.py`

```python
class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., description="HTTP hoặc SSE endpoint của MCP server")
    description: str | None = None
    headers: dict[str, str] = Field(default_factory=dict, description="Auth headers nếu cần")


class MCPServerResponse(BaseModel):
    id: str
    name: str
    url: str
    description: str | None
    is_active: bool
    tool_count: int | None = None    # số tools fetch được từ server


class MCPToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict
```

### 5.2 MCP Client

**File:** `app/services/mcp_service.py`

MCP over HTTP/SSE — server expose tools qua standard MCP protocol.

```python
import httpx

class MCPClient:
    """Client giao tiếp với một MCP server qua HTTP."""

    def __init__(self, url: str, headers: dict[str, str] = {}) -> None:
        self._url = url.rstrip("/")
        self._headers = headers

    async def list_tools(self) -> list[dict]:
        """
        Gọi MCP tools/list endpoint.
        Return list of {name, description, inputSchema}.
        Raise MCPConnectionError nếu không kết nối được.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self._url}",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                    headers={"Content-Type": "application/json", **self._headers},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("result", {}).get("tools", [])
            except httpx.HTTPError as e:
                raise MCPConnectionError(f"Cannot connect to MCP server: {e}") from e

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Gọi tools/call endpoint.
        Return result as string.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._url}",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": 2,
                },
                headers={"Content-Type": "application/json", **self._headers},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("result", {}).get("content", [])
            return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
```

**File:** `app/services/mcp_service.py` — tiếp tục

```python
class MCPService:
    def __init__(self, mcp_repo: MCPRepository) -> None:
        self._repo = mcp_repo

    async def register_server(self, user_id: str, data: MCPServerCreate) -> dict:
        """
        1. Test kết nối: gọi list_tools để verify URL hợp lệ
        2. Lưu vào DB nếu thành công
        3. Raise MCPConnectionError nếu không kết nối được
        """

    async def list_servers(self, user_id: str) -> list[dict]: ...

    async def get_server(self, user_id: str, server_id: str) -> dict: ...

    async def delete_server(self, user_id: str, server_id: str) -> None: ...

    async def toggle_active(self, user_id: str, server_id: str, is_active: bool) -> dict: ...

    async def get_tools_for_session(
        self,
        user_id: str,
        server_ids: list[str],
    ) -> list[BaseTool]:
        """
        Fetch tools từ các MCP servers được chỉ định.
        Wrap mỗi tool thành LangChain BaseTool.
        Skip server nếu không kết nối được (log warning, không raise).
        """
```

### 5.3 Dynamic MCP Tool Wrapper

**File:** `app/tools/mcp_tool.py`

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel


def create_mcp_tool(
    tool_info: dict,
    mcp_client: MCPClient,
) -> BaseTool:
    """
    Dynamically tạo LangChain tool từ MCP tool definition.
    tool_info = {"name": ..., "description": ..., "inputSchema": {...}}
    """

    class DynamicMCPTool(BaseTool):
        name: str = tool_info["name"]
        description: str = tool_info["description"]

        class ArgsSchema(BaseModel):
            # Build pydantic model từ inputSchema động
            # Dùng `create_model` từ pydantic
            pass

        async def _arun(self, **kwargs) -> str:
            return await mcp_client.call_tool(self.name, kwargs)

        def _run(self, **kwargs) -> str:
            raise NotImplementedError("Use async version")

    return DynamicMCPTool()
```

### 5.4 Tool-calling Graph

**File:** `app/graphs/tool_graph.py`

```python
# ReAct pattern: LLM → (nếu có tool_calls) → execute tools → LLM → ...
from langgraph.prebuilt import create_react_agent

def build_tool_graph(llm, tools: list[BaseTool]):
    """
    Dùng prebuilt ReAct agent từ LangGraph.
    Inject system prompt nếu có RAG context.
    """
    return create_react_agent(llm, tools, checkpointer=MemorySaver())
```

### 5.5 Updated Chat Service

**File:** `app/services/chat_service.py` — cập nhật

```python
async def chat(self, user_id, session_id, message, request: ChatRequest) -> str:
    """
    Agent selection logic:
    1. Fetch MCP tools nếu request.mcp_server_ids không rỗng
    2. Nếu có files trong session → thêm RAG context vào system prompt
    3. Nếu có tools → dùng ToolAgent (ReAct)
    4. Nếu chỉ có files → dùng RagAgent
    5. Fallback → ChatbotAgent
    """
```

### 5.6 Router

**File:** `app/routers/mcp.py`

```
POST   /mcp/servers                     → đăng ký MCP server (verify connection)
GET    /mcp/servers                     → list servers của user
GET    /mcp/servers/{id}               → chi tiết + danh sách tools
DELETE /mcp/servers/{id}               → xoá server
PATCH  /mcp/servers/{id}/toggle        → bật/tắt server
GET    /mcp/servers/{id}/tools         → live fetch tools từ server
```

### 5.7 Tests cho Phase 5

```
tests/unit/services/test_mcp_client.py
  — list_tools gọi đúng endpoint (mock httpx)
  — call_tool gọi đúng với arguments
  — MCPConnectionError khi server unreachable

tests/unit/services/test_mcp_service.py
  — register_server: test connection trước khi lưu
  — get_tools_for_session: skip server lỗi, vẫn trả tools từ server khác

tests/unit/tools/test_mcp_tool.py
  — create_mcp_tool tạo tool với đúng name, description
  — _arun gọi mcp_client.call_tool với đúng args

tests/integration/test_mcp_api.py
  — POST /mcp/servers với URL không hợp lệ → 422
  — POST /mcp/servers với server không kết nối được → 400
```

**Definition of Done Phase 5:**
- [ ] User thêm MCP server qua URL → validate connection ngay
- [ ] Tools từ MCP server được wrap thành LangChain tools
- [ ] Chat với `mcp_server_ids` → agent dùng đúng tools
- [ ] Server unreachable → skip gracefully, không crash agent
- [ ] Ownership check cho mọi MCP server operation

---

## Phase 6 — Web Search Tool

> **Mục tiêu:** Built-in web search tool, user bật/tắt per request.
> **Độ khó:** ⭐⭐⭐☆☆

### 6.1 Web Search Tool

```bash
uv add tavily-python   # hoặc duckduckgo-search
```

Ưu tiên **Tavily** (có free tier, LangChain native integration).

**File:** `app/tools/web_search_tool.py`

```python
import os
from langchain_community.tools.tavily_search import TavilySearchResults
from app.config import settings


def create_web_search_tool(max_results: int = 5) -> TavilySearchResults:
    """
    Factory cho Tavily web search tool.
    TAVILY_API_KEY phải có trong env.
    """
    os.environ["TAVILY_API_KEY"] = settings.tavily_api_key
    return TavilySearchResults(
        max_results=max_results,
        description=(
            "Search the web for current information. "
            "Use when the user asks about recent events, news, or facts "
            "that may not be in your training data."
        ),
    )
```

**File:** `app/config.py` — thêm field:

```python
tavily_api_key: str = ""     # optional — chỉ cần nếu dùng web search
```

### 6.2 Tool Assembly

**File:** `app/services/tool_service.py`

```python
class ToolService:
    """Trung tâm tập hợp tools cho một request."""

    def __init__(self, mcp_service: MCPService) -> None:
        self._mcp_service = mcp_service

    async def assemble_tools(
        self,
        user_id: str,
        mcp_server_ids: list[str],
        use_web_search: bool,
    ) -> list[BaseTool]:
        """
        Tập hợp tools từ:
        1. MCP servers được chỉ định (dynamic)
        2. Web search nếu use_web_search=True và TAVILY_API_KEY có sẵn
        Return empty list nếu không có tools nào.
        """
        tools: list[BaseTool] = []

        if mcp_server_ids:
            mcp_tools = await self._mcp_service.get_tools_for_session(user_id, mcp_server_ids)
            tools.extend(mcp_tools)

        if use_web_search and settings.tavily_api_key:
            tools.append(create_web_search_tool())

        return tools
```

### 6.3 Updated Chat Flow

**File:** `app/services/chat_service.py` — hoàn thiện

```python
async def chat(
    self,
    user_id: str,
    session_id: str,
    message: str,
    request: ChatRequest,
) -> ChatResponse:
    """
    Final agent selection logic:

    tools = await tool_service.assemble_tools(
        user_id, request.mcp_server_ids, request.use_web_search
    )
    has_files = await vector_service.has_context(session_id)

    if tools and has_files:
        → ToolAgent với RAG system prompt (context inject vào system message)
    elif tools:
        → ToolAgent
    elif has_files:
        → RagAgent
    else:
        → ChatbotAgent
    """
```

### 6.4 Tests cho Phase 6

```
tests/unit/tools/test_web_search_tool.py
  — create_web_search_tool trả TavilySearchResults
  — skip nếu TAVILY_API_KEY rỗng

tests/unit/services/test_tool_service.py
  — assemble_tools: có MCP + web search → cả hai đều có trong list
  — assemble_tools: use_web_search=True nhưng không có API key → chỉ có MCP tools
  — assemble_tools: không có gì → empty list

tests/unit/services/test_chat_service.py
  — chat với use_web_search=True → dùng ToolAgent
  — chat không có tools, không có files → dùng ChatbotAgent
  — chat không có tools, có files → dùng RagAgent
```

**Definition of Done Phase 6:**
- [ ] `use_web_search: true` trong request → agent có web search tool
- [ ] Không có Tavily key → web search bị skip, không crash
- [ ] Tool selection logic đúng cho mọi combination

---

## Phase 7 — Polish & Production Readiness

> **Mục tiêu:** Logging, rate limiting, error messages tốt, deploy-ready.
> **Độ khó:** ⭐⭐☆☆☆

### 7.1 Structured Logging

```python
# app/logging.py
import logging
import json


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "timestamp": self.formatTime(record),
        })


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=level, handlers=[handler])
```

### 7.2 Request ID Middleware

```python
# app/middleware/request_id.py
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

### 7.3 Rate Limiting (optional nếu cần)

```bash
uv add slowapi
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/sessions/{session_id}/chat")
@limiter.limit("30/minute")
async def chat(...): ...
```

### 7.4 Health Check nâng cao

```
GET /health        → {"status": "ok"}
GET /health/ready  → kiểm tra Supabase connection, Groq ping
```

### 7.5 OpenAPI Documentation

Đảm bảo mọi endpoint có:
- `summary` và `description`
- `response_model` đúng type
- `responses` khai báo error codes (401, 403, 404, 422, 429)

### 7.6 Final Integration Tests

```
tests/integration/test_full_flow.py

Scenario: User chat với files + MCP + web search
  1. POST /auth/signup (dùng Supabase test credentials)
  2. POST /sessions → tạo session
  3. POST /sessions/{id}/files → upload sample.txt
  4. POST /mcp/servers → đăng ký mock MCP server
  5. POST /sessions/{id}/chat với use_web_search=true, mcp_server_ids=[...]
  6. Verify response có content
  7. GET /sessions/{id}/messages → verify 2 messages (user + assistant)
  8. DELETE /sessions/{id} → cleanup
```

**Definition of Done Phase 7 (= Done toàn bộ dự án):**
- [ ] `make test-cov` → coverage ≥ 80% toàn bộ app
- [ ] `make lint` → không có lỗi
- [ ] Mọi endpoint có OpenAPI docs
- [ ] Structured logging hoạt động
- [ ] Full flow integration test pass

---

## Tóm tắt các Phase

| Phase | Tính năng | Độ khó | Blocker |
|---|---|---|---|
| **1** | Foundation, Auth | ⭐ | — |
| **2** | Session & Message management | ⭐⭐ | Phase 1 |
| **3** | Basic chatbot, streaming | ⭐⭐ | Phase 2 |
| **4** | File upload, RAG | ⭐⭐⭐ | Phase 3 |
| **5** | MCP server management | ⭐⭐⭐⭐ | Phase 3 |
| **6** | Web search tool | ⭐⭐⭐ | Phase 5 |
| **7** | Polish, production | ⭐⭐ | Phase 6 |

---

## Quy tắc khi implement

1. **Đọc `agents.md` trước** khi viết bất kỳ file nào — convention ở đó là luật.
2. **Mỗi Phase:** viết tests trước (`tests/`), sau đó viết implementation (`app/`).
3. **Không skip Phase** — mỗi phase build trên nền Phase trước.
4. **Commit sau mỗi Phase** với `make lint && make test` pass.
5. **Khi gặp ambiguity:** ưu tiên simplicity, ghi TODO comment, tiếp tục.
6. **External calls** (Groq, Supabase, MCP, Tavily) luôn được mock trong unit tests.
7. **Không hardcode** credentials, URLs, hay model names — luôn dùng `settings`.