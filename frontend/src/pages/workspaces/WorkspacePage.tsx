import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Modal, Input, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { api } from "../../api/client";
import { useWorkspaceStore } from "../../hooks/store";

const WorkspacePage: React.FC = () => {
  const { workspaces, setWorkspaces, loading, setLoading } = useWorkspaceStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [messageApi, contextHolder] = message.useMessage();
  const navigate = useNavigate();

  const fetchWorkspaces = async () => {
    setLoading(true);
    try { setWorkspaces(await api.listWorkspaces()); }
    catch { messageApi.error("加载课题列表失败"); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchWorkspaces(); }, []);

  const handleCreate = async () => {
    if (!title.trim()) return;
    try {
      const w = await api.createWorkspace({ title: title.trim(), description: desc.trim(), auto_generate: true });
      setIsModalOpen(false); setTitle(""); setDesc("");
      await fetchWorkspaces();
      navigate(`/chat/${w.id}`);
    } catch { messageApi.error("创建课题失败"); }
  };

  const handleDelete = async (id: string) => {
    try { await api.deleteWorkspace(id); await fetchWorkspaces(); }
    catch { messageApi.error("删除失败"); }
  };

  return (
    <div className="p-4">
      {contextHolder}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-primary">课题管理</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>新建课题</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {workspaces.map((w) => (
          <Card key={w.id} hoverable onClick={() => navigate(`/chat/${w.id}`)}
            title={w.title}
            extra={<Button type="text" danger onClick={(e) => { e.stopPropagation(); handleDelete(w.id); }}>删除</Button>}
          >
            <p className="text-secondary text-sm">{w.description || "暂无描述"}</p>
            <p className="text-secondary text-xs mt-2">{w.session_count} 个会话</p>
          </Card>
        ))}
      </div>

      {!loading && workspaces.length === 0 && (
        <div className="text-center text-secondary py-20">还没有课题，点击上方按钮创建</div>
      )}

      <Modal title="新建课题" open={isModalOpen} onOk={handleCreate} onCancel={() => setIsModalOpen(false)} okText="创建" cancelText="取消">
        <div className="space-y-4 py-4">
          <div><label className="block text-sm mb-1">课题名称</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="输入课题名称" /></div>
          <div><label className="block text-sm mb-1">描述（可选）</label>
            <Input.TextArea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="简要描述研究课题" rows={3} /></div>
        </div>
      </Modal>
    </div>
  );
};

export default WorkspacePage;
