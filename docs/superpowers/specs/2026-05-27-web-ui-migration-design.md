# ResearchMap Web UI Migration Design

**Date**: 2026-05-27
**Status**: Approved
**Reference**: `ref/autogen-main` — all UI design, colors, spacing, and reusable components sourced from here. Future designs must follow this visual style.

## 1. Overview

Migrate ResearchMap from PyQt6 desktop UI to a web-based architecture, reusing layout components from AutoGen Studio (autogen-studio frontend) while replacing page content with ResearchMap-specific views.

## 2. Motivation

- Current PyQt6 UI has limited styling flexibility (QSS restrictions, no smooth animations, dark mode is manual)
- AutoGen Studio's layout (collapsible icon sidebar + content area) is a proven, polished pattern
- Web approach enables remote access and easier future iteration

## 3. Architecture

```
ResearchMap/
├── app/                         # Existing Python backend (mostly unchanged)
│   ├── models/                  # SQLModel → reused as-is
│   ├── services/                # Business logic → reused as-is
│   ├── api/                     # NEW: FastAPI routes replacing PyQt6 signals
│   │   ├── workspaces.py
│   │   ├── sessions.py
│   │   ├── chat.py
│   │   ├── mindmap.py
│   │   └── settings.py
│   └── main.py                  # FastAPI entry point + static file serving
├── frontend/                    # NEW: React + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/          # Reused from autogen-studio
│   │   │   ├── layout.tsx
│   │   │   ├── sidebar.tsx
│   │   │   ├── contentheader.tsx
│   │   │   └── footer.tsx
│   │   ├── pages/
│   │   │   ├── workspaces/      # Workspace management (new)
│   │   │   └── chat/            # Chat view + mindmap panel (new)
│   │   └── hooks/store.ts       # Zustand stores
│   └── package.json
├── storage/                     # SQLite database (unchanged)
└── tests/
    ├── test_*.py                # Backend tests (pytest + httpx)
    └── frontend/                # Frontend tests (Vitest + RTL)
```

## 4. Navigation

Three navigation items in the collapsible sidebar:

| Icon | Label | Route | Description |
|------|-------|-------|-------------|
| Home | 课题管理 | `/workspaces` | Workspace cards grid, create/edit/delete |
| Chat | 对话 | `/chat/:workspaceId` | Chat with Agent + collapsible mindmap panel |
| Settings | 设置 | `/settings` | LLM and Agent configuration |

Mind map is NOT a standalone route — it is a collapsible right panel inside the chat page (same behavior as current PyQt6 `_toggle_mind_map()`).

## 5. Page Layouts

### 5.1 Workspace Management (`/workspaces`)

Sidebar + content area with card grid. Each card shows workspace title, description, session count. Click enters chat. "New workspace" button triggers creation dialog + optional auto-build.

### 5.2 Chat + Mindmap (`/chat/:workspaceId`)

Three-column layout within the content area:

- **Session sidebar** (left): Lists sessions for current workspace, new session button
- **Chat area** (center): Message bubbles with avatars, @mention input, streaming SSE responses. Status indicators for thinking/queued states with cancel button.
- **Mindmap panel** (right, collapsible): Interactive mind map tree using a graph visualization library

### 5.3 Settings (`/settings`)

LLM provider configuration (API key, base URL, model) and Agent toggles.

## 6. API Design

All routes under `/api/` prefix. Base URL configurable via `.env`.

### Workspaces
- `GET /api/workspaces` — list all
- `POST /api/workspaces` — create (body: title, description, auto_generate)
- `PUT /api/workspaces/:id` — update
- `DELETE /api/workspaces/:id` — cascade delete
- `POST /api/workspaces/:id/build` — trigger mindmap generation (SSE progress)

### Sessions
- `GET /api/sessions?workspace_id=` — list for workspace
- `POST /api/sessions` — create (body: workspace_id, title)
- `PUT /api/sessions/:id` — rename
- `DELETE /api/sessions/:id`

### Chat
- `GET /api/chat?session_id=` — message history
- `POST /api/chat` — send message (body: session_id, content, mentioned_agents) → SSE stream
- `POST /api/chat/cancel` — cancel active generation

### Mindmap
- `GET /api/mindmap?workspace_id=` — nodes + edges

### Settings
- `GET /api/settings` — LLM config
- `PUT /api/settings` — update
- `GET /api/settings/agents` — agent list
- `PUT /api/settings/agents/:name` — update agent

## 7. Data Flow

### Chat SSE Flow
1. Frontend POST `/api/chat` with session_id + content
2. Backend writes user message to DB, returns SSE stream
3. Backend processes via existing `MessageRouter` + Agent pipeline
4. Each token/status change pushed as SSE event
5. Frontend renders token stream in real-time, auto-scrolls
6. Status widget shows thinking/queued with cancel button
7. On completion, messages persisted in DB

### Mindmap Build Flow
1. Frontend POST `/api/workspaces/:id/build`
2. Backend fires existing `TopicBuildWorker` logic
3. Progress (nodes created, edges created, errors) streamed via SSE
4. On completion, frontend refreshes mindmap data

## 8. Component Reuse Strategy

Directly copy these files from autogen-studio frontend, with minimal modifications:

| Source | Modifications |
|--------|---------------|
| `components/layout.tsx` | Update metadata (app name, description) |
| `components/sidebar.tsx` | Replace 5 nav items with 3 ResearchMap items, change app icon |
| `components/contentheader.tsx` | None |
| `components/footer.tsx` | Update text |
| `hooks/provider.tsx` | Remove auth dependency, keep dark mode |
| `hooks/store.ts` | Adapt stores for workspace/session/chat state |

Not reused: Gatsby config, auth module, all page components (build, gallery, deploy, labs, mcp).

## 9. Tech Stack Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Build tool | Vite (not Gatsby) | Gatsby is in maintenance mode; Vite is faster, simpler |
| CSS | Tailwind CSS 3 | Matches autogen-studio, already in reused components |
| UI primitives | HeadlessUI + Ant Design | Matches autogen-studio |
| State | Zustand | Matches autogen-studio pattern |
| Graph viz | D3.js or Cytoscape.js | For interactive mindmap replacement |

## 10. Testing

- **Backend**: pytest + httpx `TestClient` for all API routes. Existing service/model tests unchanged.
- **Frontend**: Vitest + React Testing Library for component rendering, user interaction, API mocking.
- PyQt6-specific tests (`test_chat_bubble_layout.py`, `test_review_card.py`) are removed.

## 11. What Does NOT Change

- SQLModel schema (`app/models/`)
- Business logic services (`app/services/`)
- SQLite storage in `storage/`
- Agent pipeline (MessageRouter, AgentRuntime, SessionWorker, TopicBuildWorker)
