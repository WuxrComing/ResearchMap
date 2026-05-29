import { useEffect, useState } from "react";
import { Drawer, Select, Button, Switch, Input, Modal, Form, message, Popconfirm } from "antd";
import { PlusOutlined, DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import { api } from "../api/client";

interface AgentWithOverrides {
  name: string; role: string; description: string; system_prompt: string; enabled: boolean; color: string; model: string;
  is_custom: boolean;
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
  onSaveDescription: (name: string, description: string) => void;
  onSaveModel: (name: string, model: string) => void;
  onDelete: (name: string) => void;
}> = ({ workspaceId, agent, editingPrompt, setEditingPrompt, onToggle, onSaveDescription, onSaveModel, onDelete }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [descValue, setDescValue] = useState(agent.description);
  const prompt = editingPrompt[agent.name] ?? agent.system_prompt;
  const promptDirty = editingPrompt[agent.name] !== undefined && editingPrompt[agent.name] !== agent.system_prompt;
  const descDirty = descValue !== agent.description;

  useEffect(() => { setDescValue(agent.description); }, [agent.description]);

  const savePrompt = async () => {
    try {
      await api.updateWorkspaceAgent(workspaceId, agent.name, { system_prompt: prompt });
      const next = { ...editingPrompt };
      delete next[agent.name];
      setEditingPrompt(next);
      messageApi.success("已保存");
    } catch { messageApi.error("保存失败"); }
  };

  const saveDescription = async () => {
    try {
      await api.updateWorkspaceAgent(workspaceId, agent.name, { description: descValue });
      onSaveDescription(agent.name, descValue);
      messageApi.success("已保存");
    } catch { messageApi.error("保存失败"); }
  };

  return (
    <div className="space-y-4">
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
        <div className="flex items-center gap-3">
          <span className="text-xs text-secondary">{agent.enabled ? "已启用" : "已禁用"}</span>
          <Switch checked={agent.enabled} onChange={(v) => onToggle(agent.name, v)} />
        </div>
      </div>

      {/* Model selection */}
      <div>
        <label className="block text-xs font-medium text-secondary mb-1">模型选择</label>
        <Select
          value={agent.model || undefined}
          onChange={async (v) => {
            try {
              await api.updateWorkspaceAgent(workspaceId, agent.name, { model: v || "" });
              onSaveModel(agent.name, v || "");
              messageApi.success("模型已保存");
            } catch { messageApi.error("保存失败"); }
          }}
          placeholder="留空使用全局默认"
          allowClear
          style={{ width: "100%" }}
          options={[
            { label: "DeepSeek V4 Flash (快速)", value: "deepseek-v4-flash" },
            { label: "DeepSeek V4 Pro (更强)", value: "deepseek-v4-pro" },
            { label: "DeepSeek Chat", value: "deepseek-chat" },
            { label: "DeepSeek Reasoner (推理)", value: "deepseek-reasoner" },
          ]}
        />
      </div>

      {/* Editable description */}
      <div>
        <label className="block text-xs font-medium text-secondary mb-1">一句话描述</label>
        <div className="flex gap-2">
          <Input
            value={descValue}
            onChange={(e) => setDescValue(e.target.value)}
            placeholder="暂无描述"
            className="flex-1"
          />
          {descDirty && (
            <Button type="primary" size="small" onClick={saveDescription}>保存</Button>
          )}
        </div>
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
        {promptDirty && (
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

      {/* Delete button */}
      <div className="flex justify-end pt-2 border-t border-secondary/20">
        <Popconfirm title={agent.is_custom ? "确定删除此 Agent？" : "确定重置此 Agent 的修改？"} onConfirm={() => onDelete(agent.name)} okText="确定" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>{agent.is_custom ? "删除此 Agent" : "重置为默认"}</Button>
        </Popconfirm>
      </div>
    </div>
  );
};

const WorkspaceSettingsDrawer: React.FC<Props> = ({ workspaceId, workspaceTitle, open, onClose }) => {
  const [agents, setAgents] = useState<AgentWithOverrides[]>([]);
  const [editingPrompt, setEditingPrompt] = useState<Record<string, string>>({});
  const [messageApi, contextHolder] = message.useMessage();
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [agentQuery, setAgentQuery] = useState("");
  const [activeAgent, setActiveAgent] = useState<string>("");

  useEffect(() => {
    if (!open || !workspaceId) return;
    loadAgents();
  }, [open, workspaceId]);

  const loadAgents = async () => {
    try {
      const list = await api.listWorkspaceAgents(workspaceId);
      setAgents(list);
      if (list.length > 0 && !activeAgent) setActiveAgent(list[0].name);
    } catch { /* */ }
  };
  const toggleAgent = async (name: string, enabled: boolean) => {
    try {
      await api.updateWorkspaceAgent(workspaceId, name, { enabled });
      setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, enabled } : a)));
    } catch { messageApi.error("更新失败"); }
  };
  const saveDescription = (name: string, description: string) => {
    setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, description } : a)));
  };
  const saveModel = (name: string, model: string) => {
    setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, model } : a)));
  };
  const deleteAgent = async (name: string) => {
    try {
      await api.deleteWorkspaceAgent(workspaceId, name);
      setAgents((prev) => prev.filter((a) => a.name !== name));
      messageApi.success(`已删除 ${name}`);
    } catch { messageApi.error("删除失败"); }
  };
  const createAgent = async () => {
    try {
      const values = await createForm.validateFields();
      const created = await api.createWorkspaceAgent(workspaceId, values);
      setAgents((prev) => [...prev, created]);
      setCreateOpen(false);
      createForm.resetFields();
      messageApi.success(`已创建 ${values.name}`);
    } catch (e: any) {
      if (e?.errorFields) return; // form validation error
      messageApi.error(e?.message || "创建失败");
    }
  };

  const filtered = agentQuery.trim()
    ? agents.filter(a => a.name.toLowerCase().includes(agentQuery.toLowerCase()))
    : agents;

  return (
    <Drawer
      title={`课题设置 - ${workspaceTitle}`}
      open={open}
      onClose={onClose}
      width={580}
      styles={{ body: { padding: "12px 16px" } }}
    >
      {contextHolder}

      <h3 className="text-sm font-medium mb-3">Agent 管理</h3>

      <div className="flex gap-0">
        {/* Left column: search + agent list */}
        <div className="shrink-0 border-r border-secondary flex flex-col" style={{ width: 152 }}>
          <div className="flex items-center gap-1 px-2 pt-1 pb-2 border-b border-secondary/40">
            <div className="flex-1 relative">
              <SearchOutlined className="absolute left-1.5 top-1/2 -translate-y-1/2 text-secondary text-[10px]" />
              <input
                className="w-full pl-5 pr-1 py-0.5 text-[11px] bg-primary border border-secondary rounded text-primary placeholder:text-secondary focus:outline-none focus:border-accent"
                placeholder="搜索..."
                value={agentQuery}
                onChange={(e) => setAgentQuery(e.target.value)}
              />
            </div>
            <button
              onClick={() => setCreateOpen(true)}
              className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-accent text-white hover:opacity-80 transition-opacity"
              title="新增 Agent"
            >
              <PlusOutlined className="text-[10px]" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {filtered.map((agent) => {
              const isActive = activeAgent === agent.name || (!activeAgent && filtered[0]?.name === agent.name);
              return (
                <button
                  key={agent.name}
                  onClick={() => setActiveAgent(agent.name)}
                  className={`w-full text-left px-2 py-1.5 flex items-center gap-1.5 text-xs font-semibold transition-colors ${
                    isActive ? "bg-secondary text-accent" : "text-secondary hover:bg-tertiary hover:text-primary"
                  }`}
                >
                  <span
                    className="w-5 h-5 shrink-0 rounded flex items-center justify-center text-white text-[10px] font-bold"
                    style={{ backgroundColor: agent.color || "var(--color-bg-accent)" }}
                  >
                    {agent.name[0]}
                  </span>
                  <span className="truncate flex-1 font-semibold">{agent.name}</span>
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${agent.enabled ? "bg-green-500" : "bg-gray-400"}`} />
                  {agent.is_custom && <span className="text-[9px] text-accent shrink-0">自定义</span>}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right column: agent content */}
        <div className="flex-1 min-w-0 pl-3">
          {(() => {
            const active = filtered.find(a => a.name === activeAgent) || filtered[0];
            if (!active) return <div className="text-secondary text-sm p-4">暂无 Agent</div>;
            return (
              <AgentTab
                workspaceId={workspaceId}
                agent={active}
                editingPrompt={editingPrompt}
                setEditingPrompt={setEditingPrompt}
                onToggle={toggleAgent}
                onSaveDescription={saveDescription}
                onSaveModel={saveModel}
                onDelete={deleteAgent}
              />
            );
          })()}
        </div>
      </div>

      {/* Create Agent Modal */}
      <Modal
        title="新增 Agent"
        open={createOpen}
        onOk={createAgent}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        okText="创建"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" className="mt-4" initialValues={{ role: "assistant" }}>
          <Form.Item name="name" label="Agent 名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：Code Agent" />
          </Form.Item>
          <Form.Item name="role" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="model" label="模型选择">
            <Select
              placeholder="留空使用全局默认"
              allowClear
              options={[
                { label: "DeepSeek V4 Flash (快速)", value: "deepseek-v4-flash" },
                { label: "DeepSeek V4 Pro (更强)", value: "deepseek-v4-pro" },
                { label: "DeepSeek Chat", value: "deepseek-chat" },
                { label: "DeepSeek Reasoner (推理)", value: "deepseek-reasoner" },
              ]}
            />
          </Form.Item>
          <Form.Item name="color" label="标识颜色" initialValue="#07C160">
            <Input type="color" style={{ width: 48, height: 32, padding: 2 }} />
          </Form.Item>
          <Form.Item name="description" label="一句话描述">
            <Input placeholder="简述此 Agent 的职责" />
          </Form.Item>
          <Form.Item name="system_prompt" label="核心描述 (System Prompt)">
            <Input.TextArea rows={5} placeholder="此 Agent 的详细行为指令" />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
};

export default WorkspaceSettingsDrawer;
