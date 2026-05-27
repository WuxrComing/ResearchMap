import React from "react";
import { Button } from "antd";
import { PlusOutlined } from "@ant-design/icons";

interface Session { id: string; title: string; }

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

const SessionSidebar: React.FC<Props> = ({ sessions, activeId, onSelect, onCreate, onDelete }) => {
  return (
    <div className="w-56 border-r border-secondary p-2 flex flex-col">
      <Button size="small" type="primary" icon={<PlusOutlined />} onClick={onCreate} className="mb-2">新会话</Button>
      <div className="flex-1 overflow-y-auto space-y-1">
        {sessions.map((s) => (
          <div key={s.id}
            className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-sm ${s.id === activeId ? "bg-secondary/20 text-primary" : "text-secondary hover:bg-tertiary"}`}
            onClick={() => onSelect(s.id)}
          >
            <span className="truncate">{s.title}</span>
            <button className="opacity-0 hover:opacity-100 text-xs text-red-500 ml-1" onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}>✕</button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SessionSidebar;
