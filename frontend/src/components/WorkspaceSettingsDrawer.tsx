import { useEffect, useState } from "react";
import { Input, Button, Switch, Drawer, Tabs, message } from "antd";
import { api } from "../api/client";

interface AgentWithOverrides {
  name: string; role: string; description: string; system_prompt: string; enabled: boolean; color: string; model: string;
}

interface Props {
  workspaceId: string;
  workspaceTitle: string;
  open: boolean;
  onClose: () => void;
}

const AgentTab: React.FC<{
  workspaceId: string;
  agent: AgentWithOverrides;
  editingPrompt: Record<string, string>;
  setEditingPrompt: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onToggle: (name: string, enabled: boolean) => void;
}> = ({ workspaceId, agent, editingPrompt, setEditingPrompt, onToggle }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const prompt = editingPrompt[agent.name] ?? agent.system_prompt;
  const dirty = editingPrompt[agent.name] !== undefined && editingPrompt[agent.name] !== agent.system_prompt;

  const savePrompt = async () => {
    try {
      await api.updateWorkspaceAgent(workspaceId, agent.name, { system_prompt: prompt });
      const next = { ...editingPrompt };
      delete next[agent.name];
      setEditingPrompt(next);
      messageApi.success("已保存");
    } catch { messageApi.error("保存失败"); }
  };

  return (
    <div className="space-y-6">
      {contextHolder}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="w-10 h-10 shrink-0 rounded-lg flex items-center justify-center text-white text-base font-bold"
            style={{ backgroundColor: agent.color || "var(--color-bg-accent)" }}
          >
            {agent.name[0]}
          </span>
          <div>
            <div className="text-lg font-semibold text-primary">{agent.name}</div>
            <div className="text-sm text-secondary">{agent.role}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary">{agent.enabled ? "已启用" : "已禁用"}</span>
          <Switch checked={agent.enabled} onChange={(v) => onToggle(agent.name, v)} />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-secondary mb-1">一句话描述</label>
        <div className="text-sm text-primary bg-secondary/10 rounded px-3 py-2">{agent.description || "暂无描述"}</div>
      </div>

      <div>
        <label className="block text-xs font-medium text-secondary mb-1">核心描述 (System Prompt)</label>
        <Input.TextArea
          value={prompt}
          onChange={(e) => setEditingPrompt(prev => ({ ...prev, [agent.name]: e.target.value }))}
          rows={12}
          className="font-mono text-sm"
          style={{ resize: "vertical" }}
        />
        {dirty && (
          <div className="flex gap-2 mt-2">
            <Button type="primary" size="small" onClick={savePrompt}>保存</Button>
            <Button size="small" onClick={() => {
              const next = { ...editingPrompt };
              delete next[agent.name];
              setEditingPrompt(next);
            }}>取消</Button>
          </div>
        )}
      </div>
    </div>
  );
};

const WorkspaceSettingsDrawer: React.FC<Props> = ({ workspaceId, workspaceTitle, open, onClose }) => {
  const [model, setModel] = useState("");
  const [agents, setAgents] = useState<AgentWithOverrides[]>([]);
  const [editingPrompt, setEditingPrompt] = useState<Record<string, string>>({});
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    if (!open || !workspaceId) return;
    loadSettings();
    loadAgents();
  }, [open, workspaceId]);

  const loadSettings = async () => {
    try { const s = await api.getWorkspaceSettings(workspaceId); setModel(s.model); } catch { /* */ }
  };
  const loadAgents = async () => {
    try { setAgents(await api.listWorkspaceAgents(workspaceId)); } catch { /* */ }
  };
  const saveModel = async () => {
    try { await api.updateWorkspaceSettings(workspaceId, { model }); messageApi.success("模型已保存"); }
    catch { messageApi.error("保存失败"); }
  };
  const toggleAgent = async (name: string, enabled: boolean) => {
    try {
      await api.updateWorkspaceAgent(workspaceId, name, { enabled });
      setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, enabled } : a)));
    } catch { messageApi.error("更新失败"); }
  };

  const tabItems = agents.map((agent) => ({
    key: agent.name,
    label: (
      <div className="flex items-center gap-2 py-0.5">
        <span
          className="w-6 h-6 shrink-0 rounded flex items-center justify-center text-white text-xs font-bold"
          style={{ backgroundColor: agent.color || "var(--color-bg-accent)" }}
        >
          {agent.name[0]}
        </span>
        <span className="text-sm">{agent.name}</span>
        <span className={`w-1.5 h-1.5 rounded-full ${agent.enabled ? "bg-green-500" : "bg-gray-400"}`} />
      </div>
    ),
    children: (
      <AgentTab
        workspaceId={workspaceId}
        agent={agent}
        editingPrompt={editingPrompt}
        setEditingPrompt={setEditingPrompt}
        onToggle={toggleAgent}
      />
    ),
  }));

  return (
    <Drawer
      title={`课题设置 - ${workspaceTitle}`}
      open={open}
      onClose={onClose}
      width={560}
      styles={{ body: { padding: "16px" } }}
    >
      {contextHolder}

      <div className="mb-6">
        <label className="block text-sm font-medium mb-2">模型选择</label>
        <div className="flex gap-2">
          <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="留空使用全局默认" className="flex-1" />
          <Button type="primary" onClick={saveModel}>保存</Button>
        </div>
        <p className="text-xs text-secondary mt-1">留空则使用全局默认模型。当前全局默认：deepseek-v4-flash</p>
      </div>

      <div>
        <h3 className="text-sm font-medium mb-3">Agent 管理</h3>
        <Tabs
          tabPosition="left"
          items={tabItems}
          className="[&_.ant-tabs-content]:min-h-[300px]"
        />
      </div>
    </Drawer>
  );
};

export default WorkspaceSettingsDrawer;
