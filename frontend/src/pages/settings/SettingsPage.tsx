import React, { useEffect, useState } from "react";
import { Input, Button, Switch, message, Card } from "antd";
import { api } from "../../api/client";

interface Agent { name: string; role: string; description: string; enabled: boolean; }

const SettingsPage: React.FC = () => {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
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

  return (
    <div className="p-4 max-w-2xl">
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
        <div className="space-y-3">
          {agents.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between py-2 border-b border-secondary/20">
              <div><div className="text-sm font-medium text-primary">{agent.name}</div>
                <div className="text-xs text-secondary">{agent.description}</div></div>
              <Switch checked={agent.enabled} onChange={(v) => toggleAgent(agent.name, v)} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;
