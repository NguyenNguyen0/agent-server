# agents.md — agent-server

> **Mục đích chính:** Quy tắc coding convention & TDD workflow cho dự án `agent-server`.
> Đây là nguồn sự thật duy nhất (single source of truth) cho cách viết code trong dự án.

---

## Table of Contents

1. [Tech Stack & Versions](#1-tech-stack--versions)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Coding Conventions](#3-coding-conventions)
4. [TDD Workflow](#4-tdd-workflow)
5. [DRY Principles](#5-dry-principles)
6. [Agent Patterns](#6-agent-patterns)
7. [LangGraph Node Conventions](#7-langgraph-node-conventions)
8. [Supabase Conventions](#8-supabase-conventions)
9. [FastAPI Conventions](#9-fastapi-conventions)
10. [Error Handling](#10-error-handling)
11. [Linting & Formatting](#11-linting--formatting)
12. [Checklist trước khi commit](#12-checklist-trước-khi-commit)

---

## 1. Tech Stack & Versions

| Thư viện | Version tối thiểu | Ghi chú |
|---|---|---|
| Python | 3.12+ | Required |
| `uv` | latest | Package manager duy nhất — không dùng pip trực tiếp |
| `fastapi` | 0.111+ | Web framework |
| `langgraph` | 0.2+ | Agent state machine |
| `langchain` | 0.2+ | Chains, prompts, tools |
| `langserve` | 0.2+ | Expose runnable qua HTTP |
| `langchain-groq` | latest | Groq LLM integration |
| `supabase` | 2.x | Python client (async) |
| `pydantic` | v2 | Validation — KHÔNG dùng v1 |
| `pytest` | 8.x | Testing |
| `pytest-asyncio` | 0.23+ | Async test support |
| `ruff` | latest | Linting + formatting |
| `mypy` | 1.x | Static type check |

---

## 2. Cấu trúc thư mục

```
agent-server/
├── pyproject.toml
├── uv.lock
├── .env.example
├── Makefile
├── agents.md                   # file này
│
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # pydantic BaseSettings
│   ├── dependencies.py         # FastAPI DI — tất cả Depends() ở đây
│   ├── exceptions.py           # Custom exception classes
│   │
│   ├── agents/
│   │   ├── base.py             # AbstractBaseAgent
│   │   ├── chatbot_agent.py    # Conversational Chatbot
│   │   ├── rag_agent.py        # RAG Agent
│   │   └── tool_agent.py       # Tool-calling Agent
│   │
│   ├── graphs/
│   │   ├── chatbot_graph.py
│   │   ├── rag_graph.py
│   │   ├── tool_graph.py
│   │   └── nodes/              # Mỗi node là một module riêng
│   │       ├── llm_node.py
│   │       ├── retriever_node.py
│   │       ├── tool_executor_node.py
│   │       └── router_node.py
│   │
│   ├── tools/
│   │   ├── base.py
│   │   ├── search_tool.py
│   │   └── calculator_tool.py
│   │
│   ├── routers/
│   │   ├── chat.py
│   │   ├── rag.py
│   │   └── health.py
│   │
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── vector_service.py
│   │   └── session_service.py
│   │
│   ├── repositories/
│   │   ├── base.py             # Generic BaseRepository[T]
│   │   ├── message_repo.py
│   │   ├── document_repo.py
│   │   └── session_repo.py
│   │
│   ├── models/                 # Pydantic schemas (request/response)
│   │   ├── chat.py
│   │   ├── document.py
│   │   └── session.py
│   │
│   ├── prompts/                # Prompt templates — không hardcode trong agent
│   │   ├── chatbot.py
│   │   ├── rag.py
│   │   └── tool.py
│   │
│   └── utils/
│       ├── llm.py              # LLM factory
│       └── embeddings.py       # Embedding helpers
│
└── tests/
    ├── conftest.py             # Shared fixtures
    ├── unit/
    │   ├── agents/
    │   │   ├── test_chatbot_agent.py
    │   │   ├── test_rag_agent.py
    │   │   └── test_tool_agent.py
    │   ├── graphs/
    │   │   └── nodes/
    │   ├── services/
    │   └── repositories/
    └── integration/
        ├── test_chat_api.py
        └── test_rag_api.py
```

**Quy tắc cấu trúc:**
- Mỗi `app/x/y.py` phải có file test tương ứng `tests/unit/x/test_y.py`
- Không để business logic trong `routers/` — chỉ có HTTP handling
- Không để DB query trong `services/` — chỉ có business logic
- `repositories/` là layer duy nhất được phép gọi Supabase client trực tiếp

---

## 3. Coding Conventions

### 3.1 Python Style

```python
# ✅ ĐÚNG — type hints đầy đủ, return type rõ ràng
async def get_session(session_id: str) -> Session | None:
    """Lấy session theo ID. Trả None nếu không tồn tại."""
    return await self._repo.find_by_id(session_id)


# ❌ SAI — thiếu type hints, không có docstring
async def get_session(session_id):
    return await self._repo.find_by_id(session_id)
```

**Bắt buộc:**
- Type hints cho **mọi** function signature (param + return)
- Docstring ngắn cho mọi public function/class/method
- `async/await` cho mọi I/O (DB, HTTP, LLM calls)
- Không dùng `print()` — dùng `logging.getLogger(__name__)`

### 3.2 Naming

```python
# Classes → PascalCase
class RagAgent(BaseAgent): ...
class MessageRepository(BaseRepository[Message]): ...

# Functions / methods → snake_case
async def retrieve_documents(query: str) -> list[Document]: ...
async def build_rag_graph() -> CompiledGraph: ...

# Constants → UPPER_SNAKE_CASE (đặt ở đầu module)
MAX_TOKENS: int = 4096
DEFAULT_MODEL: str = "llama3-8b-8192"
TOP_K_DOCUMENTS: int = 5

# Private helpers → _single_underscore
def _format_context(docs: list[Document]) -> str: ...
def _build_system_prompt(persona: str) -> str: ...

# Type aliases → PascalCase, đặt sau imports
SessionId = str
EmbeddingVector = list[float]
DocumentList = list[Document]
```

### 3.3 Function Size & Responsibility

```python
# ✅ ĐÚNG — mỗi function 1 việc, ≤ 20 dòng
async def embed_query(query: str) -> EmbeddingVector:
    """Embed câu hỏi thành vector."""
    return await self._embedder.aembed_query(query)

async def search_similar_docs(
    embedding: EmbeddingVector,
    top_k: int = TOP_K_DOCUMENTS,
) -> DocumentList:
    """Tìm documents tương đồng trong vector store."""
    return await self._vector_service.similarity_search(embedding, top_k)

async def retrieve(self, query: str) -> DocumentList:
    """Orchestrate embed + search."""
    embedding = await self.embed_query(query)
    return await self.search_similar_docs(embedding)


# ❌ SAI — quá nhiều responsibility trong 1 function
async def process_query(query, session_id, history=None, stream=False, top_k=5):
    embedding = ...
    docs = ...
    prompt = ...
    response = ...
    await save_to_db(...)
    return response
```

### 3.4 Imports

```python
# Thứ tự: stdlib → third-party → internal
# Dùng absolute imports trong app/

# stdlib
import logging
from typing import AsyncIterator
from abc import ABC, abstractmethod

# third-party
from fastapi import Depends, HTTPException
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END

# internal
from app.config import settings
from app.models.chat import ChatInput, ChatOutput
from app.repositories.base import BaseRepository
```

### 3.5 Pydantic Models

```python
# app/models/chat.py
from pydantic import BaseModel, Field
import uuid


class ChatInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: str = Field(default="chatbot", pattern="^(chatbot|rag|tool)$")

    model_config = {"frozen": True}  # immutable — không mutate input


class ChatOutput(BaseModel):
    content: str
    session_id: str
    agent_type: str
    usage: dict[str, int] | None = None
```

---

## 4. TDD Workflow

### 4.1 Quy trình bắt buộc: Red → Green → Refactor

```
1. RED    → Viết test mô tả behavior mong muốn. Chạy → thấy FAIL (đỏ).
2. GREEN  → Viết code tối thiểu nhất để test pass. Chạy → thấy PASS (xanh).
3. REFACTOR → Cải thiện code (DRY, naming, structure). Test phải vẫn xanh.
```

> **Không được phép** viết implementation trước khi có test cho nó.

### 4.2 Test Naming Convention

```python
# Pattern: test_<behavior>_when_<condition>
# hoặc:    test_<method>_returns_<X>_given_<Y>

def test_invoke_returns_answer_when_docs_found(): ...
def test_invoke_raises_error_when_no_session(): ...
def test_retrieve_returns_empty_list_when_no_match(): ...
def test_stream_yields_tokens_when_llm_responds(): ...
```

### 4.3 Test Structure — Arrange / Act / Assert

```python
# tests/unit/agents/test_rag_agent.py
import pytest
from unittest.mock import AsyncMock
from app.agents.rag_agent import RagAgent
from app.models.chat import ChatInput


@pytest.fixture
def chat_input() -> ChatInput:
    return ChatInput(message="What is LangGraph?", session_id="sess-001")


@pytest.fixture
def rag_agent(mock_llm, mock_vector_service) -> RagAgent:
    return RagAgent(llm=mock_llm, vector_service=mock_vector_service)


class TestRagAgentInvoke:
    """Nhóm tests theo method/behavior, không theo input."""

    async def test_invoke_returns_answer_when_docs_found(
        self, rag_agent: RagAgent, chat_input: ChatInput
    ) -> None:
        # Arrange — đã setup qua fixture

        # Act
        result = await rag_agent.ainvoke(chat_input)

        # Assert
        assert result.content != ""
        assert result.session_id == chat_input.session_id

    async def test_invoke_calls_vector_service_once(
        self, rag_agent: RagAgent, chat_input: ChatInput
    ) -> None:
        # Act
        await rag_agent.ainvoke(chat_input)

        # Assert — kiểm tra interaction, không kiểm tra implementation detail
        rag_agent.vector_service.similarity_search.assert_called_once()

    async def test_invoke_raises_value_error_when_empty_message(
        self, rag_agent: RagAgent
    ) -> None:
        # Pydantic validation bắt lỗi trước khi vào agent
        with pytest.raises(ValueError):
            ChatInput(message="", session_id="sess-001")
```

### 4.4 conftest.py — Shared Fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Mock ChatGroq trả về response cố định."""
    llm = AsyncMock(spec=ChatGroq)
    llm.ainvoke.return_value = AIMessage(content="mocked response")
    llm.astream.return_value = _async_iter(["mock", "ed", " response"])
    return llm


@pytest.fixture
def mock_vector_service() -> AsyncMock:
    """Mock vector service với docs giả."""
    service = AsyncMock()
    service.similarity_search.return_value = [
        {"content": "LangGraph is a library for building stateful agents.", "score": 0.95}
    ]
    return service


@pytest.fixture
def mock_supabase() -> AsyncMock:
    """Mock Supabase async client."""
    client = AsyncMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return client


async def _async_iter(items: list[str]):
    """Helper tạo async iterator từ list."""
    for item in items:
        yield item
```

### 4.5 Pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"         # tất cả test async không cần decorator
testpaths = ["tests"]
addopts = "-v --tb=short -q"

[tool.coverage.run]
source = ["app"]
omit = ["app/main.py", "app/config.py"]

[tool.coverage.report]
fail_under = 80               # CI fail nếu coverage < 80%
show_missing = true
```

### 4.6 Quy tắc Test — Được phép & Không được phép

| | Quy tắc | Lý do |
|---|---|---|
| ✅ | Mock external dependencies (LLM, DB, HTTP) | Isolate unit under test |
| ✅ | Test behavior, không test implementation | Refactor không làm vỡ test |
| ✅ | Một `assert` chính mỗi test | Test rõ ràng, dễ debug khi fail |
| ✅ | Dùng `pytest.fixture` cho setup tái sử dụng | DRY trong tests |
| ✅ | Dùng `pytest.mark.parametrize` cho nhiều inputs | Tránh copy-paste tests |
| ❌ | Mock internal modules của app | Test trở nên giòn, không có giá trị |
| ❌ | Test nhiều behaviors trong 1 test | Khó biết thứ gì fail |
| ❌ | Hardcode giá trị magic trong test | Dùng constant hoặc fixture |
| ❌ | Skip test mà không có lý do rõ ràng | `@pytest.mark.skip(reason="...")` nếu cần |

### 4.7 Parametrize Example

```python
# tests/unit/agents/test_chatbot_agent.py
import pytest
from app.agents.chatbot_agent import ChatbotAgent
from app.models.chat import ChatInput


@pytest.mark.parametrize("message", [
    "Hello",
    "What is your name?",
    "Tell me about Python",
])
async def test_invoke_calls_llm_once_regardless_of_message(
    chatbot_agent: ChatbotAgent,
    message: str,
) -> None:
    input = ChatInput(message=message, session_id="sess-001")
    await chatbot_agent.ainvoke(input)
    chatbot_agent._llm.ainvoke.assert_called_once()
```

---

## 5. DRY Principles

### 5.1 Base Agent — không repeat interface

```python
# app/agents/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.models.chat import ChatInput, ChatOutput


class BaseAgent(ABC):
    """
    Interface chung cho tất cả agents.
    Mọi agent PHẢI kế thừa class này.
    """

    @abstractmethod
    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        """Gọi agent, chờ kết quả đầy đủ."""
        ...

    @abstractmethod
    async def astream(self, input: ChatInput) -> AsyncIterator[str]:
        """Gọi agent, stream từng token."""
        ...

    # Shared logic — subclass không cần override
    def _build_run_config(self, session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}
```

### 5.2 Base Repository — không repeat CRUD

```python
# app/repositories/base.py
from typing import Generic, TypeVar
from supabase import AsyncClient

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """
    CRUD operations dùng chung.
    Subclass chỉ override khi cần logic đặc biệt.
    """

    def __init__(self, client: AsyncClient, table_name: str) -> None:
        self._client = client
        self._table = table_name

    async def find_by_id(self, id: str) -> T | None:
        result = (
            await self._client.table(self._table)
            .select("*")
            .eq("id", id)
            .maybe_single()
            .execute()
        )
        return result.data

    async def create(self, data: dict) -> T:
        result = (
            await self._client.table(self._table)
            .insert(data)
            .execute()
        )
        return result.data[0]

    async def delete(self, id: str) -> None:
        await self._client.table(self._table).delete().eq("id", id).execute()
```

### 5.3 LLM Factory — không tạo instance lặp lại

```python
# app/utils/llm.py
from functools import lru_cache
from langchain_groq import ChatGroq
from app.config import settings


@lru_cache(maxsize=4)
def get_llm(
    model: str = settings.groq_model,
    temperature: float = 0.0,
    streaming: bool = False,
) -> ChatGroq:
    """Singleton per (model, temperature) — dùng lại thay vì tạo mới mỗi request."""
    return ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=temperature,
        streaming=streaming,
    )
```

### 5.4 Prompt Templates — không hardcode trong agent

```python
# app/prompts/rag.py
from langchain_core.prompts import ChatPromptTemplate

RAG_SYSTEM = (
    "You are a helpful assistant. "
    "Answer using ONLY the context provided. "
    "If the context does not contain the answer, say so.\n\n"
    "Context:\n{context}"
)

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM),
    ("placeholder", "{history}"),
    ("human", "{question}"),
])
```

### 5.5 FastAPI Dependencies — không repeat DI logic

```python
# app/dependencies.py — tập trung toàn bộ dependency factories
from functools import lru_cache
from supabase import AsyncClient, create_async_client
from app.config import settings
from app.utils.llm import get_llm


async def get_supabase_client() -> AsyncClient:
    """Dùng trong mọi router — không tạo client riêng mỗi router."""
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )

# Router dùng:
# db: AsyncClient = Depends(get_supabase_client)
```

---

## 6. Agent Patterns

### 6.1 Conversational Chatbot

Agent duy trì conversation history qua LangGraph checkpointer.

```python
# app/agents/chatbot_agent.py
import logging
from typing import AsyncIterator
from langchain_groq import ChatGroq
from app.agents.base import BaseAgent
from app.graphs.chatbot_graph import build_chatbot_graph
from app.models.chat import ChatInput, ChatOutput

logger = logging.getLogger(__name__)


class ChatbotAgent(BaseAgent):
    """Conversational agent với memory per session."""

    def __init__(self, llm: ChatGroq) -> None:
        self._graph = build_chatbot_graph(llm)

    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        config = self._build_run_config(input.session_id)
        result = await self._graph.ainvoke(
            {"messages": [("human", input.message)]},
            config=config,
        )
        return ChatOutput(
            content=result["messages"][-1].content,
            session_id=input.session_id,
            agent_type="chatbot",
        )

    async def astream(self, input: ChatInput) -> AsyncIterator[str]:
        config = self._build_run_config(input.session_id)
        async for chunk in self._graph.astream(
            {"messages": [("human", input.message)]},
            config=config,
            stream_mode="values",
        ):
            if chunk.get("messages"):
                yield chunk["messages"][-1].content
```

### 6.2 RAG Agent

```python
# app/agents/rag_agent.py
from langchain_groq import ChatGroq
from app.agents.base import BaseAgent
from app.graphs.rag_graph import build_rag_graph
from app.services.vector_service import VectorService
from app.models.chat import ChatInput, ChatOutput


class RagAgent(BaseAgent):
    """Agent trả lời dựa trên tài liệu từ Supabase pgvector."""

    def __init__(self, llm: ChatGroq, vector_service: VectorService) -> None:
        self._graph = build_rag_graph(llm, vector_service)

    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        config = self._build_run_config(input.session_id)
        result = await self._graph.ainvoke(
            {"query": input.message, "messages": [], "context": []},
            config=config,
        )
        return ChatOutput(
            content=result["messages"][-1].content,
            session_id=input.session_id,
            agent_type="rag",
        )
```

### 6.3 Tool-calling Agent

```python
# app/agents/tool_agent.py
from langchain_groq import ChatGroq
from langchain_core.tools import BaseTool
from app.agents.base import BaseAgent
from app.graphs.tool_graph import build_tool_graph
from app.models.chat import ChatInput, ChatOutput


class ToolAgent(BaseAgent):
    """Agent có khả năng gọi external tools."""

    def __init__(self, llm: ChatGroq, tools: list[BaseTool]) -> None:
        self._graph = build_tool_graph(llm, tools)

    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        config = self._build_run_config(input.session_id)
        result = await self._graph.ainvoke(
            {"messages": [("human", input.message)]},
            config=config,
        )
        return ChatOutput(
            content=result["messages"][-1].content,
            session_id=input.session_id,
            agent_type="tool",
        )
```

---

## 7. LangGraph Node Conventions

### 7.1 Node là pure async function

```python
# ✅ Node nhận state, trả dict update — không có side effects ngoài state
from app.graphs.rag_graph import RagState
from app.prompts.rag import RAG_PROMPT
from langchain_groq import ChatGroq


async def generate_node(state: RagState, llm: ChatGroq) -> dict:
    """Generate answer từ context đã retrieve."""
    context = "\n\n".join(state["context"])
    messages = RAG_PROMPT.format_messages(
        context=context,
        question=state["query"],
        history=state.get("messages", []),
    )
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
```

### 7.2 State Definition

```python
# app/graphs/rag_graph.py
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class RagState(TypedDict):
    query: str
    context: list[str]                           # retrieved document contents
    messages: Annotated[list[BaseMessage], add_messages]


class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


class ToolState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

### 7.3 Graph Builder Pattern

```python
# Hàm factory — không để graph là module-level singleton
from functools import partial
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver


def build_rag_graph(llm: ChatGroq, vector_service: VectorService):
    """Trả về compiled graph. Gọi một lần khi app khởi động."""
    graph = StateGraph(RagState)

    graph.add_node("retrieve", partial(retrieve_node, vector_service=vector_service))
    graph.add_node("generate", partial(generate_node, llm=llm))

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=MemorySaver())
```

---

## 8. Supabase Conventions

### 8.1 Phân chia mục đích

| Feature Supabase | Dùng ở layer | Ghi chú |
|---|---|---|
| **PostgreSQL** | `repositories/` | sessions, messages, documents |
| **pgvector** | `services/vector_service.py` | similarity search cho RAG |
| **Auth (JWT)** | `app/middleware/auth.py` | validate token mỗi request |

### 8.2 Auth Middleware

```python
# app/middleware/auth.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import AsyncClient
from app.dependencies import get_supabase_client

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncClient = Depends(get_supabase_client),
) -> dict:
    """Validate Supabase JWT — dùng làm dependency trong protected routes."""
    try:
        user = await db.auth.get_user(credentials.credentials)
        if not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user
    except Exception as e:
        raise HTTPException(status_code=401, detail="Could not validate credentials") from e
```

### 8.3 Repository — layer duy nhất gọi Supabase trực tiếp

```python
# app/repositories/message_repo.py
from supabase import AsyncClient
from app.repositories.base import BaseRepository
from app.models.chat import Message


class MessageRepository(BaseRepository[Message]):
    def __init__(self, client: AsyncClient) -> None:
        super().__init__(client, "messages")

    async def find_by_session(self, session_id: str) -> list[Message]:
        """Lấy tất cả messages của session, sorted by time."""
        result = (
            await self._client.table(self._table)
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data
```

### 8.4 Không gọi Supabase từ Agent hay Service

```python
# ❌ SAI — agent gọi Supabase trực tiếp
class RagAgent:
    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        docs = await self._supabase.table("documents").select("*").execute()
        ...

# ✅ ĐÚNG — agent → service → repository → Supabase
class RagAgent:
    def __init__(self, vector_service: VectorService) -> None:
        self._vector_service = vector_service

    async def ainvoke(self, input: ChatInput) -> ChatOutput:
        docs = await self._vector_service.search(input.message)
        ...
```

---

## 9. FastAPI Conventions

### 9.1 Router chỉ làm HTTP handling

```python
# app/routers/chat.py
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.models.chat import ChatInput, ChatOutput
from app.services.chat_service import ChatService
from app.dependencies import get_chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatOutput)
async def invoke_agent(
    input: ChatInput,
    service: ChatService = Depends(get_chat_service),
) -> ChatOutput:
    """Gọi agent, trả kết quả đầy đủ."""
    return await service.invoke(input)


@router.post("/stream")
async def stream_agent(
    input: ChatInput,
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """Gọi agent, stream từng token qua SSE."""
    return StreamingResponse(
        service.stream(input),
        media_type="text/event-stream",
    )
```

### 9.2 Protected route với Auth

```python
# Áp dụng auth dependency cho routes cần bảo vệ
from app.middleware.auth import get_current_user

@router.post("/", response_model=ChatOutput)
async def invoke_agent(
    input: ChatInput,
    current_user: dict = Depends(get_current_user),   # bắt buộc auth
    service: ChatService = Depends(get_chat_service),
) -> ChatOutput:
    return await service.invoke(input, user_id=current_user["id"])
```

---

## 10. Error Handling

### 10.1 Custom Exceptions

```python
# app/exceptions.py


class AgentServerError(Exception):
    """Base exception cho toàn bộ app."""


class AgentError(AgentServerError):
    """Lỗi khi chạy agent."""


class SessionNotFoundError(AgentServerError):
    """Session không tồn tại."""


class VectorSearchError(AgentServerError):
    """Lỗi khi thực hiện vector similarity search."""


class LLMRateLimitError(AgentServerError):
    """Groq API rate limit bị vượt."""


class DocumentNotFoundError(AgentServerError):
    """Không tìm thấy document."""


class AuthError(AgentServerError):
    """Lỗi xác thực / phân quyền."""
```

### 10.2 Exception → HTTP Mapping

```python
# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.exceptions import SessionNotFoundError, LLMRateLimitError, AuthError

app = FastAPI()


@app.exception_handler(SessionNotFoundError)
async def session_not_found_handler(request: Request, exc: SessionNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(LLMRateLimitError)
async def rate_limit_handler(request: Request, exc: LLMRateLimitError):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Retry later."})


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})
```

### 10.3 Wrap External Calls

```python
# Luôn wrap external calls và re-raise bằng internal exception
import groq
from app.exceptions import LLMRateLimitError, AgentError


async def _call_llm(self, messages: list) -> str:
    """Wrap Groq call — convert vendor exceptions sang internal."""
    try:
        response = await self._llm.ainvoke(messages)
        return response.content
    except groq.RateLimitError as e:
        raise LLMRateLimitError("Groq API rate limit exceeded") from e
    except groq.APIError as e:
        raise AgentError(f"LLM call failed: {e}") from e
```

---

## 11. Linting & Formatting

### 11.1 Ruff Config

```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes
    "I",    # isort
    "UP",   # pyupgrade
    "B",    # bugbear
    "SIM",  # simplify
    "ANN",  # annotations
]
ignore = ["ANN101", "ANN102"]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

### 11.2 Mypy Config

```toml
[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### 11.3 Makefile Commands

```makefile
.PHONY: lint format test test-cov run

lint:
	uv run ruff check app tests
	uv run ruff format --check app tests
	uv run mypy app

format:
	uv run ruff format app tests
	uv run ruff check --fix app tests

test:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v

test-cov:
	uv run pytest --cov=app --cov-report=term-missing --cov-report=html

run:
	uv run uvicorn app.main:app --reload --port 8000
```

---

## 12. Checklist trước khi commit

Chạy lần lượt — **tất cả phải pass**:

```bash
make format      # auto-fix formatting
make lint        # không có warning nào
make test-cov    # coverage ≥ 80%
```

**Code review checklist:**

- [ ] Test viết trước implementation (TDD — Red trước Green)
- [ ] Type hints đầy đủ cho tất cả function signatures
- [ ] Không có logic bị duplicate (DRY)
- [ ] External calls (LLM, DB, HTTP) đều được mock trong unit tests
- [ ] Custom exceptions thay vì `raise Exception(...)`
- [ ] Không có `print()` — chỉ dùng `logging`
- [ ] Không có hardcoded credentials, URL, hay magic numbers
- [ ] Docstring cho tất cả public functions/classes
- [ ] `repositories/` là layer duy nhất gọi Supabase trực tiếp
- [ ] Auth dependency đã được áp dụng cho protected routes

---

> **Nguyên tắc cốt lõi:** Viết code như thể người maintain sau bạn không biết context gì — vì thường đó chính là bạn, 6 tháng sau.