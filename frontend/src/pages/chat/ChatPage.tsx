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
  return <div className="w-1.5 cursor-col-resize hover:bg-accent/50 active:bg-accent shrink-0 transition-colors" onMouseDown={onMouseDown} />;
};

const ChatPage: React.FC = () => {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const { setSelectedId } = useWorkspaceStore();
  const { sessions, setSessions, activeId, setActiveId, setLoading } = useSessionStore();
  const [mindmapVisible, setMindmapVisible] = useState(true);
  const [sessionWidth, setSessionWidth] = useState(224);
  const [mindmapWidth, setMindmapWidth] = useState(320);

  const handleSessionResize = useCallback((d: number) => setSessionWidth(w => Math.max(140, Math.min(500, w + d))), []);
  const handleMindmapResize = useCallback((d: number) => setMindmapWidth(w => Math.max(200, Math.min(600, w - d))), []);

  useEffect(() => {
    if (!workspaceId) { navigate("/workspaces", { replace: true }); return; }
    setSelectedId(workspaceId);
    fetchSessions();
  }, [workspaceId]);

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
    try { const s = await api.createSession({ workspace_id: workspaceId, title: "新会话" }); await fetchSessions(); setActiveId(s.id); }
    catch { /* */ }
  };

  if (!workspaceId) return null;

  return (
    <div className="flex h-full overflow-hidden">
      <div style={{ width: sessionWidth }} className="shrink-0 h-full overflow-hidden">
        <SessionSidebar sessions={sessions} activeId={activeId} onSelect={setActiveId} onCreate={handleCreateSession}
          onDelete={async (id) => { await api.deleteSession(id); await fetchSessions(); }} />
      </div>

      <ResizeHandle onResize={handleSessionResize} />

      <div className="flex-1 flex min-w-0 h-full overflow-hidden">
        <div className="flex-1 min-w-0 h-full overflow-hidden">
          {activeId ? <ChatView sessionId={activeId} /> :
            <div className="flex items-center justify-center h-full text-secondary">选择或创建一个会话</div>}
        </div>

        {mindmapVisible && workspaceId && (
          <>
            <ResizeHandle onResize={handleMindmapResize} />
            <div style={{ width: mindmapWidth }} className="shrink-0 border-l border-secondary relative h-full overflow-hidden">
              <MindMapPanel workspaceId={workspaceId} />
              <button className="absolute top-2 right-2 p-1 rounded hover:bg-secondary text-secondary z-10" onClick={() => setMindmapVisible(false)}>◀</button>
            </div>
          </>
        )}
        {!mindmapVisible && (
          <button className="self-start mt-2 p-1 rounded hover:bg-secondary text-secondary shrink-0" onClick={() => setMindmapVisible(true)}>▶</button>
        )}
      </div>
    </div>
  );
};

export default ChatPage;
