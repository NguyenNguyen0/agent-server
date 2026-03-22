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
│  User ──► Auth (JWT tự quản lý — python-jose + bcrypt)      │
│             │                                               │
│             ▼                                               │
│  Session Manager  ──► MongoDB (sessions + messages)         │
│             │                                               │
│             ▼                                               │
│  Chat Agent (LangGraph)                                     │
│    ├── Context: uploaded files (MongoDB Atlas Vector Search) │
│    ├── File binary: MinIO (S3-compatible object storage)     │
│    ├── Tools: MCP over HTTP (per-user config)               │
│    └── Tools: Web Search (built-in, optional)               │
│             │                                               │
│             ▼                                               │
│  Groq LLM  ◄────────────────────────────────────────────── │
└─────────────────────────────────────────────────────────────┘
```

---

## MongoDB Setup (chạy trước khi bắt đầu code)

### Collections & Indexes

Chạy script sau để tạo indexes. **Không cần tạo collection trước** — MongoDB tự tạo khi insert lần đầu.

```python
# scripts/setup_db.py
# Chạy: uv run python scripts/setup_db.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ["MONGODB_DB_NAME"]


async def setup():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # users
    await db["users"].create_index("email", unique=True)

    # sessions
    await db["sessions"].create_index("user_id")
    await db["sessions"].create_index("created_at")

    # messages
    await db["messages"].create_index("session_id")
    await db["messages"].create_index([("session_id", 1), ("created_at", 1)])

    # files
    await db["files"].create_index("session_id")
    await db["files"].create_index("user_id")

    # chunks — compound index để filter theo session khi vector search
    await db["chunks"].create_index("session_id")
    await db["chunks"].create_index("file_id")

    # mcp_servers
    await db["mcp_servers"].create_index("user_id")
    await db["mcp_servers"].create_index(
        [("user_id", 1), ("name", 1)], unique=True
    )

    print("✅ Indexes created successfully")
    client.close()


asyncio.run(setup())
```

### MongoDB Atlas Vector Search Index

Tạo Vector Search index trên collection `chunks` tại **Atlas UI > Search > Create Index**:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
            "numDimensions": 768,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "session_id"
    }
  ]
}
```

> **Index name:** `chunk_embedding_index` (phải khớp với tên trong `ChunkRepository.vector_search()`).
> **Embedding model:** `BAAI/bge-base-en-v1.5` (Hugging Face Inference API).
> **numDimensions:** `768`.

---

## Phase 1 — Foundation (Skeleton, Config & Auth)

> **Mục tiêu:** Dự án chạy được, JWT auth hoạt động, CI xanh.
> **Độ khó:** ⭐☆☆☆☆

### 1.1 Khởi tạo dự án

```bash
uv init agent-server
cd agent-server
uv python pin 3.12

uv add fastapi "uvicorn[standard]" pydantic-settings python-multipart
uv add motor pymongo "python-jose[cryptography]" "passlib[bcrypt]"
uv add langgraph langchain "langchain-groq" langserve
uv add --dev pytest pytest-asyncio pytest-cov respx ruff mypy mongomock-motor
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

    # MongoDB
    mongodb_uri: str                          # mongodb+srv://... hoặc mongodb://localhost:27017
    mongodb_db_name: str = "agent_server"

    # Hugging Face Inference API (Embeddings)
    huggingface_api_key: str
    hf_embedding_model: str = "BAAI/bge-base-en-v1.5"  # 768 dims

    # MinIO (S3-compatible object storage)
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False
    minio_bucket_name: str = "uploads"

    # JWT
    jwt_secret: str                           # random string dài ≥ 32 chars
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7    # 7 ngày

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_file_size_mb: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Optional
    tavily_api_key: str = ""


settings = Settings()
```

**File:** `.env.example`

```bash
# Groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# MongoDB
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/
MONGODB_DB_NAME=agent_server

# Hugging Face Inference API
HUGGINGFACE_API_KEY=hf_...
HF_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET_NAME=uploads

# JWT
JWT_SECRET=your-super-secret-key-at-least-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

# App
APP_ENV=development
LOG_LEVEL=INFO

# Optional
TAVILY_API_KEY=tvly-...
```

### 1.3 MongoDB Client

**File:** `app/db/mongo.py`

Implement theo `agents.md § 8.3`:
- `get_client()` → singleton `AsyncIOMotorClient`
- `get_db()` → `AsyncIOMotorDatabase`
- `close_client()` → gọi khi shutdown
- `to_str_id(doc)` → convert `_id` ObjectId sang `id` string
- `to_object_id(id_str)` → parse string sang `ObjectId`, raise `ValueError` nếu invalid

**File:** `app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.mongo import get_client, close_client
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = get_client()
    await client.admin.command("ping")   # verify connection on startup
    yield
    await close_client()


app = FastAPI(title="agent-server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.routers import health
app.include_router(health.router)
```

### 1.4 Security Utilities

**File:** `app/utils/security.py`

Implement theo `agents.md § 8.2`:
- `hash_password(plain)` → bcrypt hash
- `verify_password(plain, hashed)` → bool
- `create_access_token(user_id)` → JWT string
- `decode_token(token)` → user_id string, raise `JWTError` nếu invalid/expired

### 1.5 Auth Endpoints

**File:** `app/routers/auth.py`

```
POST /auth/register   → {email, password} → {access_token, token_type}
POST /auth/login      → {email, password} → {access_token, token_type}
GET  /auth/me         → header Bearer → user info
```

**File:** `app/repositories/user_repo.py`

Kế thừa `BaseRepository`. Thêm:
- `find_by_email(email: str) -> dict | None`

**File:** `app/services/auth_service.py`

```python
class AuthService:
    async def register(self, email: str, password: str) -> str:
        """
        1. Check email chưa tồn tại (raise DuplicateEmailError nếu có)
        2. Hash password
        3. Insert vào collection users
        4. Return access_token
        """

    async def login(self, email: str, password: str) -> str:
        """
        1. Tìm user theo email
        2. Verify password
        3. Return access_token
        4. Raise InvalidCredentialsError nếu sai
        """
```

**File:** `app/middleware/auth.py`

Implement `get_current_user` theo `agents.md § 8.3`.

### 1.6 Tests cho Phase 1

```
tests/unit/db/test_mongo.py
  — to_str_id chuyển đúng _id → id
  — to_object_id parse valid string thành công
  — to_object_id raise ValueError với string không hợp lệ

tests/unit/utils/test_security.py
  — hash_password trả hash khác với plain text
  — verify_password: đúng password → True, sai → False
  — create_access_token tạo JWT có thể decode
  — decode_token: token hợp lệ → user_id, expired → JWTError

tests/unit/services/test_auth_service.py
  — register: email mới → tạo user + trả token
  — register: email trùng → raise DuplicateEmailError
  — login: đúng credentials → trả token
  — login: sai password → raise InvalidCredentialsError

tests/integration/test_auth_api.py
  — POST /auth/register → 201 + access_token
  — POST /auth/login → 200 + access_token
  — GET /auth/me với valid token → 200 + user info
  — GET /auth/me với invalid token → 401
```

**Definition of Done Phase 1:**
- [ ] `make test` pass 100%
- [ ] `make lint` không có lỗi
- [ ] `GET /health` → `200`
- [ ] Register + Login + token validation hoạt động
- [ ] MongoDB ping thành công khi startup

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
    role: str                    # "user" | "assistant" | "tool"
    content: str
    tool_calls: dict | None = None
    created_at: datetime


class MessageHistory(BaseModel):
    messages: list[MessageResponse]
```

### 2.2 Repositories

**File:** `app/repositories/session_repo.py`

Kế thừa `BaseRepository`. Thêm:
- `find_by_user(user_id: str) -> list[dict]` — sorted by `created_at DESC`
- `find_by_user_and_id(user_id: str, session_id: str) -> dict | None`
  — filter cả `user_id` lẫn `_id` để đảm bảo ownership

**File:** `app/repositories/message_repo.py`

Kế thừa `BaseRepository`. Thêm:
- `find_by_session(session_id: str) -> list[dict]` — sorted by `created_at ASC`
- `create_message(session_id, role, content, tool_calls=None) -> dict`
- `delete_by_session(session_id: str) -> int` — xoá toàn bộ messages, trả count

### 2.3 Services

**File:** `app/services/session_service.py`

```python
class SessionService:
    def __init__(self, session_repo: SessionRepository, message_repo: MessageRepository) -> None: ...

    async def create_session(self, user_id: str, title: str) -> dict:
        """Insert session mới với user_id, title, created_at, updated_at."""

    async def list_sessions(self, user_id: str) -> list[dict]:
        """Trả sessions của user, mới nhất trước."""

    async def get_session(self, user_id: str, session_id: str) -> dict:
        """Raise SessionNotFoundError nếu không tìm thấy hoặc không phải owner."""

    async def delete_session(self, user_id: str, session_id: str) -> None:
        """
        1. Verify ownership
        2. Xoá messages của session
        3. Xoá session document
        """

    async def get_history(self, user_id: str, session_id: str) -> list[dict]:
        """Verify ownership rồi trả message history."""
```

### 2.4 Router

**File:** `app/routers/sessions.py`

```
POST   /sessions                           → tạo session mới
GET    /sessions                           → list sessions của current user
GET    /sessions/{session_id}             → chi tiết session
DELETE /sessions/{session_id}             → xoá session + messages
GET    /sessions/{session_id}/messages    → lịch sử messages
```

Tất cả routes require `current_user = Depends(get_current_user)`.

### 2.5 Tests cho Phase 2

```
tests/unit/repositories/test_session_repo.py
  — find_by_user trả đúng sessions của user (dùng mongomock-motor)
  — find_by_user_and_id: đúng owner → doc, sai owner → None
  — delete_by_id: document không còn trong collection

tests/unit/repositories/test_message_repo.py
  — find_by_session sorted đúng thứ tự ASC
  — create_message trả doc có id string
  — delete_by_session xoá đúng số lượng

tests/unit/services/test_session_service.py
  — create_session trả dict với id, user_id, title
  — get_session: không tìm thấy → SessionNotFoundError
  — delete_session: xoá cả session lẫn messages

tests/integration/test_sessions_api.py
  — CRUD sessions end-to-end
  — User A không thể đọc/xoá session của User B → 404
```

**Definition of Done Phase 2:**
- [ ] CRUD sessions hoạt động đúng
- [ ] Ownership check nghiêm ngặt (không dùng RLS — phải check trong service)
- [ ] Delete session → cascade xoá messages
- [ ] Coverage ≥ 80%

---

## Phase 3 — Basic Chat (Conversational Chatbot)

> **Mục tiêu:** User chat trong session, lịch sử lưu vào MongoDB, LLM trả lời có context.
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

### 3.2 Pydantic Models

**File:** `app/models/chat.py`

```python
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8192)
    agent_type: str = Field(default="chatbot", pattern="^(chatbot|rag|tool)$")
    use_web_search: bool = False
    mcp_server_ids: list[str] = []


class ChatResponse(BaseModel):
    content: str
    session_id: str
    message_id: str       # MongoDB id của assistant message vừa lưu
```

### 3.3 Chat Service

**File:** `app/services/chat_service.py`

```python
class ChatService:
    async def chat(
        self,
        user_id: str,
        session_id: str,
        request: ChatRequest,
    ) -> ChatResponse:
        """
        1. Verify session ownership (raise SessionNotFoundError nếu không phải owner)
        2. Load message history từ MongoDB (MessageRepository.find_by_session)
        3. Convert history sang LangChain message format
        4. Invoke ChatbotAgent với history inject vào state
        5. Lưu user message vào MongoDB
        6. Lưu assistant response vào MongoDB
        7. Return ChatResponse với message_id của assistant message
        """

    async def stream_chat(
        self,
        user_id: str,
        session_id: str,
        request: ChatRequest,
    ) -> AsyncIterator[str]:
        """
        Stream version:
        1-4. Giống chat()
        5. Lưu user message
        6. Stream từng token, collect full response
        7. Lưu full response vào MongoDB
        8. Yield SSE events: data: {"token": "..."}\n\n
        9. Yield data: [DONE]\n\n
        """
```

### 3.4 Router

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

### 3.5 Tests cho Phase 3

```
tests/unit/graphs/test_chatbot_graph.py
  — graph.ainvoke với mock LLM trả response đúng
  — thread_id khác nhau → state độc lập

tests/unit/agents/test_chatbot_agent.py
  — ainvoke với mock graph trả ChatOutput
  — astream yield từng chunk

tests/unit/services/test_chat_service.py
  — chat: verify ownership trước khi invoke
  — chat: load history, inject vào agent
  — chat: lưu 2 messages vào MongoDB sau mỗi turn
  — stream_chat: yield tokens, lưu full response sau khi done

tests/integration/test_chat_api.py
  — POST /sessions/{id}/chat → 200 + content
  — POST /sessions/{id}/chat/stream → 200 + SSE events
  — GET /sessions/{id}/messages → 2 messages sau 1 turn chat
```

**Definition of Done Phase 3:**
- [ ] Chat trả lời đúng với LLM
- [ ] History được load và inject vào context mỗi turn
- [ ] 2 messages (user + assistant) được lưu vào MongoDB sau mỗi turn
- [ ] SSE streaming emit đúng format

---

## Phase 4 — File Upload & RAG Context

> **Mục tiêu:** User upload file vào session, agent tự dùng nội dung file khi chat.
> **Độ khó:** ⭐⭐⭐☆☆

### 4.1 Supported File Types

| Loại | Xử lý |
|---|---|
| `.txt`, `.md` | Đọc trực tiếp |
| `.pdf` | `pypdf` extract text |
| `.docx` | `python-docx` extract text |
| `.csv`, `.json` | Đọc raw text |

```bash
uv add pypdf python-docx langchain-text-splitters langchain-huggingface huggingface-hub minio
```

### 4.2 MinIO Setup

**File:** `app/storage/minio.py`

```python
from functools import lru_cache

from minio import Minio
from app.config import settings


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """Singleton MinIO client cho binary file storage."""
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def get_bucket_name() -> str:
    """Bucket mặc định cho file upload binary."""
    return settings.minio_bucket_name  # giá trị đã chốt: "uploads"
```

### 4.3 Embedding Setup

**File:** `app/utils/embeddings.py`

```python
from functools import lru_cache

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from app.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> HuggingFaceEndpointEmbeddings:
    """
    Singleton HuggingFace API embedding client (serverless inference).
    Model: BAAI/bge-base-en-v1.5 (768 dims).
    """
    return HuggingFaceEndpointEmbeddings(
        model=settings.hf_embedding_model,
        huggingfacehub_api_token=settings.huggingface_api_key,
    )
```

### 4.4 File Processing Pipeline

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
        1. Validate: size ≤ MAX_FILE_SIZE_MB → raise FileTooLargeError
        2. Validate: mime_type trong whitelist → raise UnsupportedFileTypeError
        3. Upload binary lên MinIO bucket `uploads`, lưu object_key + etag
           object_key convention: {user_id}/{session_id}/{file_id}/{filename}
        4. Lưu metadata vào collection files
           {session_id, user_id, filename, mime_type, size_bytes, minio_bucket, object_key, etag}
        5. Extract text từ file content (theo mime_type)
        6. Chunk text dùng RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)
        7. Embed từng chunk bằng Hugging Face Inference API
           model: BAAI/bge-base-en-v1.5 (768 dims)
        8. Batch insert chunks vào collection chunks {file_id, session_id, user_id, content, chunk_index, embedding}
        9. Return file metadata dict
        """

    async def delete_file(self, user_id: str, file_id: str) -> None:
        """
        1. Verify ownership (file.user_id == user_id)
        2. Xoá chunks của file (ChunkRepository.delete_by_file)
        3. Xoá MinIO object theo (bucket, object_key)
        4. Xoá file metadata document
        """

    async def list_files(self, user_id: str, session_id: str) -> list[dict]:
        """List files của session — verify ownership qua user_id."""

    def _extract_text(self, content: bytes, mime_type: str) -> str:
        """Dispatch sang đúng extractor theo mime_type."""

    def _extract_pdf(self, content: bytes) -> str: ...
    def _extract_docx(self, content: bytes) -> str: ...
    def _extract_plain(self, content: bytes) -> str: ...
```

**File:** `app/services/vector_service.py`

```python
class VectorService:
    def __init__(self, chunk_repo: ChunkRepository, embedder) -> None: ...

    async def similarity_search(
        self,
        query: str,
        session_id: str,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict]:
        """
        1. Embed query bằng embedder
        2. Gọi ChunkRepository.vector_search (MongoDB $vectorSearch)
        3. Trả list chunks sorted by score DESC
        """

    async def has_context(self, session_id: str) -> bool:
        """True nếu session có ít nhất 1 chunk."""
```

**File:** `app/repositories/chunk_repo.py`

Implement `vector_search` và `count_by_session` theo `agents.md § 8.5`.
Thêm `delete_by_file(file_id: str) -> int`.

### 4.5 RAG Graph

**File:** `app/graphs/nodes/retriever_node.py`

```python
async def retriever_node(state: RagState, vector_service: VectorService) -> dict:
    """Tìm chunks liên quan, inject vào state context."""
    last_human = [m for m in state["messages"] if m.type == "human"][-1]
    chunks = await vector_service.similarity_search(
        query=last_human.content,
        session_id=state["session_id"],
    )
    return {"context": [c["content"] for c in chunks]}
```

**File:** `app/graphs/rag_graph.py`

Graph flow: `retrieve` → `generate` → `END`

State: `RagState` với `query`, `session_id`, `context`, `messages`.

### 4.6 Smart Agent Router trong Chat Service

```python
# app/services/chat_service.py — cập nhật
async def _select_agent(
    self,
    request: ChatRequest,
    session_id: str,
    tools: list[BaseTool],
    has_files: bool,
) -> BaseAgent:
    """
    Ưu tiên:
    1. Có tools → ToolAgent (tools bao gồm RAG context nếu có files)
    2. Có files, không có tools → RagAgent
    3. Fallback → ChatbotAgent
    """
```

### 4.7 Router

**File:** `app/routers/files.py`

```
POST   /sessions/{session_id}/files              → upload file
GET    /sessions/{session_id}/files              → list files
DELETE /sessions/{session_id}/files/{file_id}   → xoá file + chunks
```

### 4.8 Tests cho Phase 4

```
tests/unit/services/test_file_service.py
  — _extract_text: pdf/txt/docx trả đúng text (dùng fixture files)
  — upload_file: size quá lớn → FileTooLargeError, không lưu DB
  — upload_file: mime type không hỗ trợ → UnsupportedFileTypeError
    — upload_file: thành công → minio.put_object + file_repo.create + chunk_repo.insert_many được gọi
    — delete_file: thành công → minio.remove_object được gọi đúng bucket/object_key

tests/unit/services/test_vector_service.py
  — similarity_search embed query rồi gọi chunk_repo.vector_search
    — similarity_search dùng embedding model BAAI/bge-base-en-v1.5 (768 dims)
  — has_context: count > 0 → True, count == 0 → False

tests/unit/repositories/test_chunk_repo.py
  — delete_by_file xoá đúng số chunks

tests/unit/graphs/test_rag_graph.py
  — retriever_node inject context vào state
  — generate_node dùng context trong prompt (verify RAG_PROMPT được gọi)

tests/integration/test_files_api.py
  — POST /files với txt → 200, chunks được tạo trong DB
  — POST /files > 20MB → 413
  — DELETE /files/{id} → 200, chunks bị xoá
  — Chat sau upload → response relevant với nội dung file

tests/fixtures/
├── sample.txt
├── sample.pdf
└── sample.docx
```

**Definition of Done Phase 4:**
- [ ] Upload PDF/TXT/DOCX hoạt động
- [ ] Text extracted → chunked → embedded → lưu vào MongoDB chunks collection
- [ ] Atlas Vector Search index tạo thành công
- [ ] Chat trong session có files → tự dùng RAG
- [ ] Delete file → xoá sạch chunks và MinIO object
- [ ] File > MAX_FILE_SIZE_MB → `413`

---

## Phase 5 — MCP Server Management

> **Mục tiêu:** User thêm MCP server qua HTTP URL, agent dùng tools từ MCP khi chat.
> **Độ khó:** ⭐⭐⭐⭐☆

### 5.1 Pydantic Models

**File:** `app/models/mcp.py`

```python
from pydantic import BaseModel, Field, HttpUrl


class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., description="HTTP hoặc SSE endpoint của MCP server")
    description: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class MCPServerResponse(BaseModel):
    id: str
    name: str
    url: str
    description: str | None
    is_active: bool
    tool_count: int | None = None


class MCPToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict
```

### 5.2 MCP Repository

**File:** `app/repositories/mcp_repo.py`

Kế thừa `BaseRepository`. Thêm:
- `find_by_user(user_id: str) -> list[dict]`
- `find_by_user_and_id(user_id: str, server_id: str) -> dict | None`
- `find_active_by_ids(user_id: str, server_ids: list[str]) -> list[dict]`

### 5.3 MCP Client

**File:** `app/services/mcp_service.py`

Giữ nguyên `MCPClient` từ phiên bản trước — không phụ thuộc vào database.

```python
import httpx
from app.exceptions import MCPConnectionError


class MCPClient:
    def __init__(self, url: str, headers: dict[str, str] = {}) -> None:
        self._url = url.rstrip("/")
        self._headers = headers

    async def list_tools(self) -> list[dict]:
        """Gọi tools/list, raise MCPConnectionError nếu lỗi."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    self._url,
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                    headers={"Content-Type": "application/json", **self._headers},
                )
                resp.raise_for_status()
                return resp.json().get("result", {}).get("tools", [])
            except httpx.HTTPError as e:
                raise MCPConnectionError(f"Cannot connect: {e}") from e

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Gọi tools/call, trả về content string."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url,
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": 2,
                },
                headers={"Content-Type": "application/json", **self._headers},
            )
            resp.raise_for_status()
            content = resp.json().get("result", {}).get("content", [])
            return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
```

**File:** `app/services/mcp_service.py` — tiếp tục

```python
class MCPService:
    def __init__(self, mcp_repo: MCPRepository) -> None:
        self._repo = mcp_repo

    async def register_server(self, user_id: str, data: MCPServerCreate) -> dict:
        """
        1. Tạo MCPClient với data.url và data.headers
        2. Gọi list_tools() để verify kết nối — raise MCPConnectionError nếu fail
        3. Insert vào MongoDB với user_id, name, url, headers, is_active=True
        4. Return server document
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
        1. Fetch active servers từ MongoDB theo server_ids và user_id
        2. Với mỗi server: gọi list_tools()
        3. Wrap mỗi tool thành DynamicMCPTool (xem agents.md § 6.3)
        4. Skip server lỗi (log warning), không raise
        5. Return list tất cả tools từ tất cả servers
        """
```

### 5.4 Dynamic MCP Tool Wrapper

**File:** `app/tools/mcp_tool.py`

```python
from langchain_core.tools import BaseTool
from pydantic import create_model


def create_mcp_tool(tool_info: dict, mcp_client: MCPClient) -> BaseTool:
    """Tạo LangChain tool động từ MCP tool definition."""

    class DynamicMCPTool(BaseTool):
        name: str = tool_info["name"]
        description: str = tool_info.get("description", "")

        async def _arun(self, **kwargs) -> str:
            return await mcp_client.call_tool(self.name, kwargs)

        def _run(self, **kwargs) -> str:
            raise NotImplementedError("Use async version")

    return DynamicMCPTool()
```

### 5.5 Tool-calling Graph

**File:** `app/graphs/tool_graph.py`

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver


def build_tool_graph(llm, tools: list[BaseTool]):
    """ReAct agent — LLM tự quyết định khi nào gọi tool."""
    return create_react_agent(llm, tools, checkpointer=MemorySaver())
```

### 5.6 Router

**File:** `app/routers/mcp.py`

```
POST   /mcp/servers                  → đăng ký + verify connection
GET    /mcp/servers                  → list servers của user
GET    /mcp/servers/{id}            → chi tiết + tools list
DELETE /mcp/servers/{id}            → xoá server
PATCH  /mcp/servers/{id}/toggle     → {is_active: bool} → bật/tắt
GET    /mcp/servers/{id}/tools      → live fetch tools từ server
```

### 5.7 Tests cho Phase 5

```
tests/unit/services/test_mcp_client.py
  — list_tools gọi đúng endpoint JSON-RPC (mock httpx với respx)
  — call_tool trả đúng content text
  — HTTPError → MCPConnectionError

tests/unit/services/test_mcp_service.py
  — register_server: verify connection trước khi insert vào MongoDB
  — register_server: server unreachable → MCPConnectionError, không insert
  — get_tools_for_session: skip server lỗi, vẫn trả tools từ server còn lại

tests/unit/tools/test_mcp_tool.py
  — create_mcp_tool trả tool với đúng name, description
  — _arun gọi mcp_client.call_tool với đúng arguments

tests/integration/test_mcp_api.py
  — POST /mcp/servers với server unreachable → 400
  — POST /mcp/servers với URL invalid format → 422
  — Ownership check: user A không xoá được server của user B → 404
```

**Definition of Done Phase 5:**
- [ ] Register MCP server → verify live connection ngay
- [ ] Tools wrap thành LangChain tools đúng
- [ ] Chat với `mcp_server_ids` → agent dùng đúng tools
- [ ] Server lỗi → skip gracefully
- [ ] Ownership check cho mọi operation

---

## Phase 6 — Web Search Tool

> **Mục tiêu:** Built-in web search, user opt-in per request.
> **Độ khó:** ⭐⭐⭐☆☆

### 6.1 Web Search Tool

```bash
uv add tavily-python
```

**File:** `app/tools/web_search_tool.py`

```python
import os
from langchain_community.tools.tavily_search import TavilySearchResults
from app.config import settings


def create_web_search_tool(max_results: int = 5) -> TavilySearchResults:
    """Factory — chỉ gọi khi settings.tavily_api_key không rỗng."""
    os.environ["TAVILY_API_KEY"] = settings.tavily_api_key
    return TavilySearchResults(
        max_results=max_results,
        description=(
            "Search the web for current information. "
            "Use for recent events, news, or facts not in training data."
        ),
    )


def web_search_available() -> bool:
    """True nếu Tavily API key được cấu hình."""
    return bool(settings.tavily_api_key)
```

### 6.2 Tool Assembly Service

**File:** `app/services/tool_service.py`

```python
class ToolService:
    """Tập hợp tools cho mỗi request từ MCP servers + web search."""

    def __init__(self, mcp_service: MCPService) -> None:
        self._mcp_service = mcp_service

    async def assemble_tools(
        self,
        user_id: str,
        mcp_server_ids: list[str],
        use_web_search: bool,
    ) -> list[BaseTool]:
        """
        Kết hợp:
        1. Tools từ MCP servers (dynamic, per-request)
        2. Web search nếu use_web_search=True và Tavily key có sẵn
        Return empty list nếu không có tools nào.
        """
        tools: list[BaseTool] = []

        if mcp_server_ids:
            mcp_tools = await self._mcp_service.get_tools_for_session(user_id, mcp_server_ids)
            tools.extend(mcp_tools)

        if use_web_search and web_search_available():
            tools.append(create_web_search_tool())

        return tools
```

### 6.3 Final Chat Service — hoàn thiện agent selection

**File:** `app/services/chat_service.py`

```python
async def chat(
    self,
    user_id: str,
    session_id: str,
    request: ChatRequest,
) -> ChatResponse:
    """
    Complete flow:

    # 1. Verify ownership
    session = await self._session_service.get_session(user_id, session_id)

    # 2. Assemble tools
    tools = await self._tool_service.assemble_tools(
        user_id, request.mcp_server_ids, request.use_web_search
    )

    # 3. Check RAG context
    has_files = await self._vector_service.has_context(session_id)

    # 4. Select agent
    if tools:
        # Nếu có files, inject RAG context vào system message của ToolAgent
        agent = ToolAgent(llm, tools)
    elif has_files:
        agent = RagAgent(llm, vector_service)
    else:
        agent = ChatbotAgent(llm)

    # 5. Load + inject history
    # 6. Invoke agent
    # 7. Save user + assistant messages to MongoDB
    # 8. Return ChatResponse
    """
```

### 6.4 Tests cho Phase 6

```
tests/unit/tools/test_web_search_tool.py
  — web_search_available: có key → True, rỗng → False
  — create_web_search_tool trả TavilySearchResults

tests/unit/services/test_tool_service.py
  — assemble_tools: mcp_ids + use_web_search=True → cả hai loại tool
  — assemble_tools: use_web_search=True nhưng không có key → chỉ MCP tools
  — assemble_tools: không có gì → empty list

tests/unit/services/test_chat_service.py
  — Không tools + không files → ChatbotAgent
  — Không tools + có files → RagAgent
  — Có tools → ToolAgent (dù có hay không có files)
  — Có tools + có files → ToolAgent (RAG context inject vào system)
```

**Definition of Done Phase 6:**
- [ ] `use_web_search: true` → agent có Tavily tool
- [ ] Không có Tavily key → skip, không crash
- [ ] Agent selection logic đúng cho mọi combination
- [ ] Tool list được assembled per-request (không cache cross-request)

---

## Phase 7 — Polish & Production Readiness

> **Mục tiêu:** Logging, observability, deploy-ready.
> **Độ khó:** ⭐⭐☆☆☆

### 7.1 Structured Logging

**File:** `app/logging_config.py`

```python
import logging
import json
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        })


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
```

### 7.2 Request ID Middleware

**File:** `app/middleware/request_id.py`

```python
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

### 7.3 Rate Limiting

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

**File:** `app/routers/health.py`

```
GET /health        → {"status": "ok", "version": "1.0.0"}
GET /health/ready  → kiểm tra MongoDB ping + Groq reachable
```

```python
@router.get("/health/ready")
async def readiness():
    checks = {}
    try:
        await get_client().admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception:
        checks["mongodb"] = "error"
    return {"status": "ready" if all(v == "ok" for v in checks.values()) else "degraded", **checks}
```

### 7.5 OpenAPI Documentation

Đảm bảo mọi endpoint có `summary`, `description`, `response_model`, và `responses` khai báo error codes.

### 7.6 Final Integration Test

```
tests/integration/test_full_flow.py

Scenario: Full user journey
  1. POST /auth/register → lấy token
  2. POST /sessions → tạo session
  3. POST /sessions/{id}/files → upload sample.txt
  4. POST /mcp/servers → đăng ký mock MCP server (dùng respx mock)
  5. POST /sessions/{id}/chat
     body: {message: "...", use_web_search: false, mcp_server_ids: ["..."]}
  6. GET /sessions/{id}/messages → verify 2 messages
  7. DELETE /sessions/{id} → cleanup
  8. Verify messages + chunks bị xoá cascade
```

**Definition of Done Phase 7 (= Done toàn bộ dự án):**
- [ ] `make test-cov` → coverage ≥ 80%
- [ ] `make lint` → không có lỗi
- [ ] Mọi endpoint có OpenAPI docs
- [ ] JSON structured logging
- [ ] `/health/ready` kiểm tra MongoDB
- [ ] Full flow integration test pass

---

## Tóm tắt các Phase

| Phase | Tính năng | Độ khó | Blocker |
|---|---|---|---|
| **1** | Foundation, JWT Auth, MongoDB setup | ⭐ | — |
| **2** | Session & Message management | ⭐⭐ | Phase 1 |
| **3** | Basic chatbot, SSE streaming | ⭐⭐ | Phase 2 |
| **4** | File upload, RAG (MinIO + Atlas Vector Search) | ⭐⭐⭐ | Phase 3 |
| **5** | MCP server management | ⭐⭐⭐⭐ | Phase 3 |
| **6** | Web search tool + agent selection | ⭐⭐⭐ | Phase 5 |
| **7** | Polish, production readiness | ⭐⭐ | Phase 6 |

---

## Quy tắc khi implement

1. **Đọc `agents.md` trước** — convention ở đó là luật.
2. **Mỗi Phase:** viết tests trước (`tests/`), sau đó implementation (`app/`).
3. **Không skip Phase** — mỗi phase build trên nền Phase trước.
4. **Commit sau mỗi Phase** với `make lint && make test` pass.
5. **Khi gặp ambiguity:** ưu tiên simplicity, ghi `TODO:` comment, tiếp tục.
6. **External calls** (Groq, MongoDB, MCP, Tavily) luôn được mock trong unit tests.
7. **Không hardcode** credentials, connection strings, model names — luôn dùng `settings`.
8. **ObjectId:** luôn dùng `to_str_id()` trước khi trả document ra ngoài repository.
9. **Ownership:** không bao giờ tin `session_id` từ URL mà không verify `user_id` trong DB.
