import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useWorkspaceStore, useSessionStore } from "../../hooks/store";
import { api } from "../../api/client";
import SessionSidebar from "./SessionSidebar";
import ChatView from "./ChatView";
import MindMapPanel from "../mindmap/MindMapPanel";

const ChatPage: React.FC = () => {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const { workspaces, setWorkspaces, setSelectedId } = useWorkspaceStore();
  const { sessions, setSessions, activeId, setActiveId, setLoading } = useSessionStore();
  const [mindmapVisible, setMindmapVisible] = useState(true);

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
    try {
      const data = await api.listWorkspaces();
      setWorkspaces(data);
    } catch { /* */ }
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

  return (
    <div className="flex h-[calc(100vh-120px)]">
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

      {/* Column 2: Session list */}
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreateSession}
        onDelete={async (id) => { await api.deleteSession(id); await fetchSessions(); }}
      />

      {/* Column 3 + 4: Chat + Mindmap */}
      <div className="flex-1 flex">
        <div className="flex-1">
          {activeId ? (
            <ChatView sessionId={activeId} />
          ) : (
            <div className="flex items-center justify-center h-full text-secondary">
              选择或创建一个会话
            </div>
          )}
        </div>
        {mindmapVisible && workspaceId && (
          <div className="w-80 border-l border-secondary relative">
            <MindMapPanel workspaceId={workspaceId} />
            <button
              className="absolute top-2 right-2 p-1 rounded hover:bg-secondary text-secondary"
              onClick={() => setMindmapVisible(false)}
            >
              ◀
            </button>
          </div>
        )}
        {!mindmapVisible && (
          <button
            className="self-start mt-2 p-1 rounded hover:bg-secondary text-secondary"
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
