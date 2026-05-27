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
    <div className="w-full h-full border-r border-secondary p-2 flex flex-col">
      <Button size="small" type="primary" icon={<PlusOutlined />} onClick={onCreate} className="mb-2">新会话</Button>
      <div className="flex-1 overflow-y-auto scroll space-y-1">
        {sessions.map((s) => {
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
