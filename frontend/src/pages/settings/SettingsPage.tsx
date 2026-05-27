import { useEffect, useState } from "react";
import { Input, Button, Switch, message, Card } from "antd";
import { api } from "../../api/client";

interface Agent {
  name: string; role: string; description: string; system_prompt: string; enabled: boolean; color: string;
}

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
    try { await api.updateAgent(name, { enabled }); setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, enabled } : a))); }
    catch { messageApi.error("更新失败"); }
  };

  const saveSystemPrompt = async (name: string) => {
    const prompt = editingPrompt[name];
    if (prompt === undefined) return;
    try {
      await api.updateAgent(name, { system_prompt: prompt });
      setAgents(prev => prev.map(a => a.name === name ? { ...a, system_prompt: prompt } : a));
      const next = { ...editingPrompt };
      delete next[name];
      setEditingPrompt(next);
      messageApi.success("核心描述已保存");
    } catch { messageApi.error("保存失败"); }
  };

  return (
    <div className="p-4 max-w-3xl">
      {contextHolder}
      <h1 className="text-2xl font-bold text-primary mb-6">设置</h1>

      <Card title="LLM 配置" className="mb-4">
        <div className="space-y-4">
          <div><label className="block text-sm mb-1">API Key</label>
            <Input.Password value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="输入新的 API Key（留空不修改）" /></div>
          <div><label className="block text-sm mb-1">Base URL</label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} /></div>
          <div><label className="block text-sm mb-1">Model</label>
            <Input value={model} onChange={(e) => setModel(e.target.value)} /></div>
          <Button type="primary" onClick={saveSettings}>保存</Button>
        </div>
      </Card>

      <Card title="Agent 管理">
        <div className="space-y-2">
          {agents.map((agent) => (
            <div key={agent.name} className="border border-secondary/30 rounded-lg overflow-hidden">
              {/* Header row */}
              <div className="flex items-center justify-between px-3 py-2.5 bg-secondary/10">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span
                    className="w-6 h-6 shrink-0 rounded flex items-center justify-center text-white text-xs font-bold"
                    style={{ backgroundColor: agent.color || "var(--color-bg-accent)" }}
                  >
                    {agent.name[0]}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-primary">{agent.name}</div>
                    <div className="text-xs text-secondary truncate">{agent.description || "暂无描述"}</div>
                  </div>
                </div>
                <Switch checked={agent.enabled} onChange={(v) => toggleAgent(agent.name, v)} size="small" />
              </div>

              {/* System prompt section */}
              <div className="px-3 py-2">
                <div className="text-xs font-medium text-secondary mb-1">核心描述 (System Prompt)</div>
                <Input.TextArea
                  value={editingPrompt[agent.name] ?? agent.system_prompt}
                  onChange={(e) => setEditingPrompt(prev => ({ ...prev, [agent.name]: e.target.value }))}
                  rows={4}
                  className="text-xs font-mono"
                  style={{ resize: "vertical" }}
                />
                {editingPrompt[agent.name] !== undefined && editingPrompt[agent.name] !== agent.system_prompt && (
                  <div className="flex gap-2 mt-2">
                    <Button size="small" type="primary" onClick={() => saveSystemPrompt(agent.name)}>保存</Button>
                    <Button size="small" onClick={() => {
                      const next = { ...editingPrompt };
                      delete next[agent.name];
                      setEditingPrompt(next);
                    }}>取消</Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;
