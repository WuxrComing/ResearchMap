const BASE = "/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, { headers: { "Content-Type": "application/json", ...options?.headers }, ...options });
  if (!res.ok) { const err = await res.text(); throw new Error(err || `${res.status}`); }
  return res.json();
}

export const api = {
  listWorkspaces: () => request<any[]>("/workspaces"),
  createWorkspace: (body: { title: string; description: string; auto_generate?: boolean }) => request<any>("/workspaces", { method: "POST", body: JSON.stringify(body) }),
  updateWorkspace: (id: string, body: { title: string; description: string }) => request<any>(`/workspaces/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteWorkspace: (id: string) => request<any>(`/workspaces/${id}`, { method: "DELETE" }),

  listSessions: (workspaceId: string) => request<any[]>(`/sessions?workspace_id=${workspaceId}`),
  createSession: (body: { workspace_id: string; title: string }) => request<any>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  updateSession: (id: string, body: { workspace_id: string; title: string }) => request<any>(`/sessions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSession: (id: string) => request<any>(`/sessions/${id}`, { method: "DELETE" }),

  listMessages: (sessionId: string) => request<any[]>(`/chat?session_id=${sessionId}`),
  sendMessage: (body: { session_id: string; content: string }) =>
    fetch(`${BASE}/chat`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }),
  cancelMessage: (sessionId: string, rootUserMessageId: string) =>
    request<any>("/chat/cancel", { method: "POST", body: JSON.stringify({ session_id: sessionId, root_user_message_id: rootUserMessageId }) }),

  getMindmap: (workspaceId: string) => request<any>(`/mindmap?workspace_id=${workspaceId}`),

  getSettings: () => request<any>("/settings"),
  updateSettings: (body: any) => request<any>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  listAgents: () => request<any[]>("/settings/agents"),
  updateAgent: (name: string, body: any) => request<any>(`/settings/agents/${name}`, { method: "PUT", body: JSON.stringify(body) }),
};
