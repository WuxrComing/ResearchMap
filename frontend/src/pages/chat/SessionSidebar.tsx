import { useState } from "react";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";

interface Session { id: string; title: string; }

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

const SessionSidebar: React.FC<Props> = ({ sessions, activeId, onSelect, onCreate, onDelete }) => {
  const [query, setQuery] = useState("");

  const filtered = query.trim()
    ? sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase()))
    : sessions;

  return (
    <div className="w-full h-full border-r border-secondary p-2 flex flex-col">
      <div className="flex items-center gap-1 mb-2">
        <div className="flex-1 relative">
          <SearchOutlined className="absolute left-2 top-1/2 -translate-y-1/2 text-secondary text-xs" />
          <input
            className="w-full pl-7 pr-2 py-1 text-sm bg-primary border border-secondary rounded text-primary placeholder:text-secondary focus:outline-none focus:border-accent"
            placeholder="搜索会话..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button
          onClick={onCreate}
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded bg-accent text-white hover:opacity-80 transition-opacity"
          title="新建会话"
        >
          <PlusOutlined className="text-xs" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto space-y-1">
        {filtered.map((s) => {
          const isActive = s.id === activeId;
          return (
            <div key={s.id} className="relative">
              {isActive && (
                <div className="bg-accent absolute top-1 left-0.5 z-50 h-8 w-1 bg-opacity-80 rounded" />
              )}
              <div
                className={`flex items-center justify-between ml-1 px-2 py-1.5 rounded cursor-pointer text-sm ${
                  isActive ? "bg-secondary text-primary" : "text-secondary hover:bg-tertiary hover:text-accent"
                }`}
                onClick={() => onSelect(s.id)}
              >
                <span className="truncate">{s.title}</span>
                <button
                  className="opacity-0 hover:opacity-100 text-xs text-red-500 ml-1 shrink-0"
                  onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                >✕</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SessionSidebar;
