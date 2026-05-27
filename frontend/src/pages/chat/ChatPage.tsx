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
  const { setSelectedId } = useWorkspaceStore();
  const { sessions, setSessions, activeId, setActiveId, setLoading } = useSessionStore();
  const [mindmapVisible, setMindmapVisible] = useState(true);

  useEffect(() => {
    if (!workspaceId) { navigate("/workspaces"); return; }
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
    <div className="flex h-[calc(100vh-120px)]">
      <SessionSidebar sessions={sessions} activeId={activeId} onSelect={setActiveId} onCreate={handleCreateSession}
        onDelete={async (id) => { await api.deleteSession(id); await fetchSessions(); }} />
      <div className="flex-1 flex">
        <div className="flex-1">
          {activeId ? <ChatView sessionId={activeId} /> :
            <div className="flex items-center justify-center h-full text-secondary">选择或创建一个会话</div>}
        </div>
        {mindmapVisible && workspaceId && (
          <div className="w-80 border-l border-secondary relative">
            <MindMapPanel workspaceId={workspaceId} />
            <button className="absolute top-2 right-2 p-1 rounded hover:bg-secondary text-secondary" onClick={() => setMindmapVisible(false)}>◀</button>
          </div>
        )}
        {!mindmapVisible && (
          <button className="self-start mt-2 p-1 rounded hover:bg-secondary text-secondary" onClick={() => setMindmapVisible(true)}>▶</button>
        )}
      </div>
    </div>
  );
};

export default ChatPage;
