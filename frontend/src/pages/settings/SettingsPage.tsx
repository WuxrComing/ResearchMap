import { useEffect, useState } from "react";
import { Input, Button, Switch, message, Card, Tabs } from "antd";
import { api } from "../../api/client";

interface Agent {
  name: string; role: string; description: string; system_prompt: string; enabled: boolean; color: string;
}

const AgentTab: React.FC<{
  agent: Agent;
  editingPrompt: Record<string, string>;
  setEditingPrompt: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onToggle: (name: string, enabled: boolean) => void;
}> = ({ agent, editingPrompt, setEditingPrompt, onToggle }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const prompt = editingPrompt[agent.name] ?? agent.system_prompt;
  const dirty = editingPrompt[agent.name] !== undefined && editingPrompt[agent.name] !== agent.system_prompt;

  const savePrompt = async () => {
    try {
      await api.updateAgent(agent.name, { system_prompt: prompt });
      const next = { ...editingPrompt };
      delete next[agent.name];
      setEditingPrompt(next);
      messageApi.success("已保存");
    } catch { messageApi.error("保存失败"); }
  };

  return (
    <div className="space-y-6">
      {contextHolder}
      {/* Header */}
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

      {/* One-line description */}
      <div>
        <label className="block text-xs font-medium text-secondary mb-1">一句话描述</label>
        <div className="text-sm text-primary bg-secondary/10 rounded px-3 py-2">{agent.description || "暂无描述"}</div>
      </div>

      {/* System prompt */}
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

const SettingsPage: React.FC = () => {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [editingPrompt, setEditingPrompt] = useState<Record<string, string>>({});
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => { loadSettings(); loadAgents(); }, []);

  const loadSettings = async () => {
    try { const s = await api.getSettings(); setBaseUrl(s.base_url); setModel(s.model); } catch { /* */ }
  };
  const loadAgents = async () => {
    try { setAgents(await api.listAgents()); } catch { /* */ }
  };
  const saveSettings = async () => {
    try { await api.updateSettings({ api_key: apiKey || undefined, base_url: baseUrl, model }); messageApi.success("设置已保存"); }
    catch { messageApi.error("保存失败"); }
  };
  const toggleAgent = async (name: string, enabled: boolean) => {
    try {
      await api.updateAgent(name, { enabled });
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
        agent={agent}
        editingPrompt={editingPrompt}
        setEditingPrompt={setEditingPrompt}
        onToggle={toggleAgent}
      />
    ),
  }));

  return (
    <div className="p-4 max-w-5xl">
      {contextHolder}
      <h1 className="text-2xl font-bold text-primary mb-6">设置</h1>

      <Card title="LLM 配置" className="mb-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-40">
            <label className="block text-sm mb-1">API Key</label>
            <Input.Password value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="输入新的 API Key" />
          </div>
          <div className="flex-1 min-w-60">
            <label className="block text-sm mb-1">Base URL</label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          </div>
          <div className="w-40">
            <label className="block text-sm mb-1">Model</label>
            <Input value={model} onChange={(e) => setModel(e.target.value)} />
          </div>
          <Button type="primary" onClick={saveSettings}>保存</Button>
        </div>
      </Card>

      <Card title="Agent 管理" styles={{ body: { padding: 0 } }}>
        <Tabs
          tabPosition="left"
          items={tabItems}
          className="[&_.ant-tabs-content]:min-h-[400px]"
          style={{ minHeight: 400 }}
        />
      </Card>
    </div>
  );
};

export default SettingsPage;
