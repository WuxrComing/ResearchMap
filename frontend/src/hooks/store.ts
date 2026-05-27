import { create } from "zustand";

interface ConfigStore {
  sidebar: { isExpanded: boolean };
  header: { title: string; breadcrumbs: { name: string; href: string; current?: boolean }[] };
  setSidebarState: (state: Partial<{ isExpanded: boolean }>) => void;
  setHeader: (header: ConfigStore["header"]) => void;
}

export const useConfigStore = create<ConfigStore>((set) => ({
  sidebar: { isExpanded: false },
  header: { title: "课题管理", breadcrumbs: [{ name: "课题管理", href: "/workspaces", current: true }] },
  setSidebarState: (state) => set((prev) => ({ sidebar: { ...prev.sidebar, ...state } })),
  setHeader: (header) => set({ header }),
}));

// ---- Workspaces ----
interface Workspace { id: string; title: string; description: string; session_count: number; created_at: string; updated_at: string; }
interface WorkspaceStore { workspaces: Workspace[]; selectedId: string | null; loading: boolean; setWorkspaces: (w: Workspace[]) => void; setSelectedId: (id: string | null) => void; setLoading: (l: boolean) => void; }
export const useWorkspaceStore = create<WorkspaceStore>((set) => ({ workspaces: [], selectedId: null, loading: false, setWorkspaces: (w) => set({ workspaces: w }), setSelectedId: (id) => set({ selectedId: id }), setLoading: (l) => set({ loading: l }) }));

// ---- Sessions ----
interface Session { id: string; workspace_id: string; title: string; created_at: string; updated_at: string; }
interface SessionStore { sessions: Session[]; activeId: string | null; loading: boolean; setSessions: (s: Session[]) => void; setActiveId: (id: string | null) => void; setLoading: (l: boolean) => void; }
export const useSessionStore = create<SessionStore>((set) => ({ sessions: [], activeId: null, loading: false, setSessions: (s) => set({ sessions: s }), setActiveId: (id) => set({ activeId: id }), setLoading: (l) => set({ loading: l }) }));

// ---- Chat ----
interface ChatMessage { id: string; session_id: string; role: string; content: string; agent_name: string | null; review_status: string | null; created_at: string | null; }
interface ChatStore { messages: ChatMessage[]; streaming: boolean; pendingAgents: { agent_name: string; state: string }[]; setMessages: (m: ChatMessage[]) => void; addMessage: (m: ChatMessage) => void; setStreaming: (s: boolean) => void; setPendingAgents: (a: { agent_name: string; state: string }[]) => void; }
export const useChatStore = create<ChatStore>((set) => ({ messages: [], streaming: false, pendingAgents: [], setMessages: (m) => set({ messages: m }), addMessage: (msg) => set((prev) => ({ messages: [...prev.messages, msg] })), setStreaming: (s) => set({ streaming: s }), setPendingAgents: (a) => set({ pendingAgents: a }) }));
