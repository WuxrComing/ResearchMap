import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useWorkspaceStore, useSessionStore } from "../../hooks/store";
import { api } from "../../api/client";
import SessionSidebar from "./SessionSidebar";
import ChatView from "./ChatView";
import MindMapPanel from "../mindmap/MindMapPanel";

const ResizeHandle: React.FC<{ onResize: (delta: number) => void }> = ({ onResize }) => {
  const dragging = useRef(false);
  const startX = useRef(0);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      startX.current = e.clientX;
      onResize(delta);
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [onResize]);

  return (
    <div
      className="w-1.5 cursor-col-resize hover:bg-accent/50 active:bg-accent shrink-0 transition-colors"
      onMouseDown={onMouseDown}
    />
  );
};

const ChatPage: React.FC = () => {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const { workspaces, setWorkspaces, setSelectedId } = useWorkspaceStore();
  const { sessions, setSessions, activeId, setActiveId, setLoading } = useSessionStore();
  const [mindmapVisible, setMindmapVisible] = useState(true);
  const [sessionWidth, setSessionWidth] = useState(224);
  const [mindmapWidth, setMindmapWidth] = useState(320);

  const handleSessionResize = useCallback((delta: number) => {
    setSessionWidth((w) => Math.max(140, Math.min(500, w + delta)));
  }, []);

  const handleMindmapResize = useCallback((delta: number) => {
    setMindmapWidth((w) => Math.max(200, Math.min(600, w - delta)));
  }, []);

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      if (workspaces.length > 0) {
        navigate(`/chat/${workspaces[0].id}`, { replace: true });
      } else {
        navigate("/workspaces", { replace: true });
      }
      return;
    }
    setSelectedId(workspaceId);
    fetchSessions();
  }, [workspaceId, workspaces]);

  const fetchWorkspaces = async () => {
    try { setWorkspaces(await api.listWorkspaces()); } catch { /* */ }
  };

  const fetchSessions = async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const data = await api.listSessions(workspaceId);
      setSessions(data);
      if (data.length > 0 && !activeId) setActiveId(data[0].id);
    } catch { /* */ }
    finally { setLoading(false); }
  };

  const handleCreateSession = async () => {
    if (!workspaceId) return;
    try {
      const s = await api.createSession({ workspace_id: workspaceId, title: "新会话" });
      await fetchSessions();
      setActiveId(s.id);
    } catch { /* */ }
  };

  if (!workspaceId) return null;

  return (
    <div className="flex h-full">
      {/* Column 1: Workspace list */}
      <div className="w-48 border-r border-secondary flex flex-col">
        <div className="text-xs font-semibold text-secondary uppercase px-3 py-2 tracking-wider">课题</div>
        <div className="flex-1 overflow-y-auto">
          {workspaces.map((w) => (
            <div
              key={w.id}
              onClick={() => { setActiveId(null); navigate(`/chat/${w.id}`); }}
              className={`px-3 py-1.5 text-sm cursor-pointer truncate ${
                w.id === workspaceId
                  ? "bg-secondary/20 text-primary font-medium"
                  : "text-secondary hover:bg-tertiary hover:text-primary"
              }`}
            >
              {w.title}
            </div>
          ))}
        </div>
      </div>

      {/* Column 2: Session list (resizable) */}
      <div style={{ width: sessionWidth }} className="shrink-0">
        <SessionSidebar
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={handleCreateSession}
          onDelete={async (id) => { await api.deleteSession(id); await fetchSessions(); }}
        />
      </div>

      <ResizeHandle onResize={handleSessionResize} />

      {/* Column 3 + 4: Chat + Mindmap */}
      <div className="flex-1 flex min-w-0">
        <div className="flex-1 min-w-0">
          {activeId ? (
            <ChatView sessionId={activeId} />
          ) : (
            <div className="flex items-center justify-center h-full text-secondary">
              选择或创建一个会话
            </div>
          )}
        </div>

        {mindmapVisible && workspaceId && (
          <>
            <ResizeHandle onResize={handleMindmapResize} />
            <div style={{ width: mindmapWidth }} className="shrink-0 border-l border-secondary relative">
              <MindMapPanel workspaceId={workspaceId} />
              <button
                className="absolute top-2 right-2 p-1 rounded hover:bg-secondary text-secondary z-10"
                onClick={() => setMindmapVisible(false)}
              >
                ◀
              </button>
            </div>
          </>
        )}
        {!mindmapVisible && (
          <button
            className="self-start mt-2 p-1 rounded hover:bg-secondary text-secondary shrink-0"
            onClick={() => setMindmapVisible(true)}
          >
            ▶
          </button>
        )}
      </div>
    </div>
  );
};

export default ChatPage;
