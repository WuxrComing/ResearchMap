import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface IBreadcrumb {
  name: string;
  href: string;
  icon?: React.ReactNode;
  current?: boolean;
}

export interface IAgentFlowSettings {
  direction: "TB" | "LR";
  showLabels: boolean;
  showGrid: boolean;
  showTokens: boolean;
  showMessages: boolean;
  showMiniMap?: boolean;
}

interface IHeaderState {
  title: string;
  breadcrumbs?: IBreadcrumb[];
}

interface ISidebarState {
  isExpanded: boolean;
  isPinned: boolean;
}

export interface IConfigState {
  messages: any[];
  setMessages: (messages: any[]) => void;
  session: any | null;
  setSession: (session: any | null) => void;
  sessions: any[];
  setSessions: (sessions: any[]) => void;
  version: string | null;
  setVersion: (version: string | null) => void;

  header: IHeaderState;
  setHeader: (header: Partial<IHeaderState>) => void;
  setBreadcrumbs: (breadcrumbs: IBreadcrumb[]) => void;

  sidebar: ISidebarState;
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  setSidebarState: (state: Partial<ISidebarState>) => void;
  collapseSidebar: () => void;
  expandSidebar: () => void;
  toggleSidebar: () => void;

  agentFlow: IAgentFlowSettings;
  setAgentFlowSettings: (settings: Partial<IAgentFlowSettings>) => void;
}

const DEFAULT_AGENT_FLOW_SETTINGS: IAgentFlowSettings = {
  direction: "TB",
  showLabels: true,
  showGrid: true,
  showTokens: true,
  showMessages: true,
  showMiniMap: false,
};

export const useConfigStore = create<IConfigState>()(
  persist(
    (set) => ({
      messages: [],
      setMessages: (messages) => set({ messages }),
      session: null,
      setSession: (session) => set({ session }),
      sessions: [],
      setSessions: (sessions) => set({ sessions }),
      version: null,
      setVersion: (version) => set({ version }),

      header: { title: "", breadcrumbs: [] },
      setHeader: (newHeader) =>
        set((state) => ({ header: { ...state.header, ...newHeader } })),
      setBreadcrumbs: (breadcrumbs) =>
        set((state) => ({ header: { ...state.header, breadcrumbs } })),

      agentFlow: DEFAULT_AGENT_FLOW_SETTINGS,
      setAgentFlowSettings: (newSettings) =>
        set((state) => ({ agentFlow: { ...state.agentFlow, ...newSettings } })),

      sidebar: { isExpanded: true, isPinned: false },
      sidebarWidth: 288,
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth }),
      setSidebarState: (newState) =>
        set((state) => ({ sidebar: { ...state.sidebar, ...newState } })),
      collapseSidebar: () =>
        set((state) => ({ sidebar: { ...state.sidebar, isExpanded: false } })),
      expandSidebar: () =>
        set((state) => ({ sidebar: { ...state.sidebar, isExpanded: true } })),
      toggleSidebar: () =>
        set((state) => ({ sidebar: { ...state.sidebar, isExpanded: !state.sidebar.isExpanded } })),
    }),
    {
      name: "app-sidebar-state",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ sidebar: state.sidebar, sidebarWidth: state.sidebarWidth, agentFlow: state.agentFlow }),
    }
  )
);

// ---- ResearchMap-specific stores ----
interface Workspace { id: string; title: string; description: string; session_count: number; created_at: string; updated_at: string; }
interface WorkspaceStore { workspaces: Workspace[]; selectedId: string | null; loading: boolean; setWorkspaces: (w: Workspace[]) => void; setSelectedId: (id: string | null) => void; setLoading: (l: boolean) => void; }
export const useWorkspaceStore = create<WorkspaceStore>((set) => ({ workspaces: [], selectedId: null, loading: false, setWorkspaces: (w) => set({ workspaces: w }), setSelectedId: (id) => set({ selectedId: id }), setLoading: (l) => set({ loading: l }) }));

interface Session { id: string; workspace_id: string; title: string; created_at: string; updated_at: string; }
interface SessionStore { sessions: Session[]; activeId: string | null; loading: boolean; setSessions: (s: Session[]) => void; setActiveId: (id: string | null) => void; setLoading: (l: boolean) => void; }
export const useSessionStore = create<SessionStore>((set) => ({ sessions: [], activeId: null, loading: false, setSessions: (s) => set({ sessions: s }), setActiveId: (id) => set({ activeId: id }), setLoading: (l) => set({ loading: l }) }));

interface ChatMessage { id: string; session_id: string; role: string; content: string; agent_name: string | null; review_status: string | null; created_at: string | null; }
interface ChatStore { messages: ChatMessage[]; streaming: boolean; pendingAgents: { agent_name: string; state: string }[]; setMessages: (m: ChatMessage[]) => void; addMessage: (m: ChatMessage) => void; setStreaming: (s: boolean) => void; setPendingAgents: (a: { agent_name: string; state: string }[]) => void; }
export const useChatStore = create<ChatStore>((set) => ({ messages: [], streaming: false, pendingAgents: [], setMessages: (m) => set({ messages: m }), addMessage: (msg) => set((prev) => ({ messages: [...prev.messages, msg] })), setStreaming: (s) => set({ streaming: s }), setPendingAgents: (a) => set({ pendingAgents: a }) }));
