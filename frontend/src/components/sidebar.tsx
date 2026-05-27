import { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useConfigStore, useWorkspaceStore } from "../hooks/store";
import { Tooltip } from "antd";
import { Settings, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { SearchOutlined, PlusOutlined } from "@ant-design/icons";
import Icon from "./icons";

const classNames = (...classes: (string | undefined | boolean)[]) => classes.filter(Boolean).join(" ");

type SidebarProps = { link: string; meta?: { title: string; description: string }; isMobile: boolean };

const Sidebar = ({ link: _link, meta, isMobile }: SidebarProps) => {
  const { sidebar, setHeader, setSidebarState } = useConfigStore();
  const { workspaces, setWorkspaces } = useWorkspaceStore();
  const { isExpanded } = sidebar;
  const navigate = useNavigate();
  const location = useLocation();
  const showFull = isMobile || isExpanded;
  const [query, setQuery] = useState("");

  const currentWorkspaceId = location.pathname.startsWith("/chat/")
    ? location.pathname.split("/chat/")[1] : null;

  const fetchWorkspaces = () => {
    fetch("/api/workspaces").then(r => r.json()).then(d => setWorkspaces(d)).catch(() => {});
  };

  useEffect(() => { fetchWorkspaces(); }, []);

  const filtered = query.trim()
    ? workspaces.filter(w => w.title.toLowerCase().includes(query.toLowerCase()))
    : workspaces;

  const handleWorkspaceClick = (id: string, title: string) => {
    setHeader({ title, breadcrumbs: [{ name: title, href: `/chat/${id}`, current: true }] });
    navigate(`/chat/${id}`);
  };

  const handleCreateWorkspace = async () => {
    const title = window.prompt("课题名称：");
    if (!title?.trim()) return;
    try {
      const res = await fetch("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), description: "", auto_generate: true }),
      });
      const w = await res.json();
      fetchWorkspaces();
      handleWorkspaceClick(w.id, w.title);
    } catch { /* */ }
  };

  return (
    <div className={classNames(
      "flex grow z-50 flex-col gap-y-5 overflow-y-auto overflow-x-hidden border-r border-secondary bg-primary",
      "transition-all duration-300 ease-in-out",
      showFull ? "w-72 px-6" : "w-16 px-2"
    )}>
      {/* Logo */}
      <div className={`flex h-16 items-center ${showFull ? "gap-x-3" : "ml-2"}`}>
        <Link to="/" className="w-8 text-right text-accent hover:opacity-80 transition-opacity">
          <Icon icon="app" size={8} />
        </Link>
        {showFull && (
          <div className="flex flex-col" style={{ minWidth: "200px" }}>
            <span className="text-base font-semibold text-primary">{meta?.title || "Research Map"}</span>
            <span className="text-xs text-secondary">{meta?.description || "科研思维导图 Agent"}</span>
          </div>
        )}
      </div>

      {/* Workspace list with search */}
      {showFull ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <div className="flex items-center gap-1 mb-2">
            <div className="flex-1 relative">
              <SearchOutlined className="absolute left-2 top-1/2 -translate-y-1/2 text-secondary text-xs" />
              <input
                className="w-full pl-7 pr-2 py-1 text-sm bg-primary border border-secondary rounded text-primary placeholder:text-secondary focus:outline-none focus:border-accent"
                placeholder="搜索课题..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button
              onClick={handleCreateWorkspace}
              className="shrink-0 w-7 h-7 flex items-center justify-center rounded bg-accent text-white hover:opacity-80 transition-opacity"
              title="新建课题"
            >
              <PlusOutlined className="text-xs" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto overflow-x-hidden space-y-0.5">
            {filtered.map((w) => {
              const isActive = w.id === currentWorkspaceId;
              return (
                <div key={w.id} className="relative">
                  {isActive && <div className="bg-accent absolute top-1 left-0.5 z-50 h-8 w-1 bg-opacity-80 rounded" />}
                  <button onClick={() => handleWorkspaceClick(w.id, w.title)}
                    className={classNames(
                      "w-full text-left flex gap-x-2 rounded-md p-2 text-sm font-medium",
                      isActive ? "bg-secondary text-primary" : "text-secondary hover:bg-tertiary hover:text-accent"
                    )}>
                    <span className="w-6 h-6 shrink-0 rounded flex items-center justify-center text-white text-xs font-bold"
                      style={{ backgroundColor: isActive ? "var(--color-bg-accent)" : "var(--color-text-secondary)" }}>
                      {w.title[0]}
                    </span>
                    <span className="truncate">{w.title}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center gap-1">
          <Tooltip title="新建课题" placement="right">
            <button onClick={handleCreateWorkspace}
              className="w-10 h-10 rounded-md flex items-center justify-center text-secondary hover:bg-tertiary hover:text-accent">
              <PlusOutlined className="text-sm" />
            </button>
          </Tooltip>
          {workspaces.map((w) => {
            const isActive = w.id === currentWorkspaceId;
            return (
              <Tooltip key={w.id} title={w.title} placement="right">
                <button onClick={() => handleWorkspaceClick(w.id, w.title)}
                  className={classNames(
                    "w-10 h-10 rounded-md flex items-center justify-center text-sm font-bold",
                    isActive ? "bg-secondary text-accent" : "text-secondary hover:bg-tertiary hover:text-accent"
                  )}>
                  {w.title[0]}
                </button>
              </Tooltip>
            );
          })}
        </div>
      )}

      {/* Settings at bottom */}
      <div className={classNames("mb-4", !showFull && "flex flex-col items-center gap-1")}>
        {!showFull && !isMobile ? (
          <>
            <Tooltip title="设置" placement="right">
              <Link to="/settings" onClick={() => setHeader({ title: "Settings", breadcrumbs: [{ name: "Settings", href: "/settings", current: true }] })}
                className="group flex gap-x-3 rounded-md p-2 text-sm text-primary hover:text-accent hover:bg-secondary justify-center">
                <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
              </Link>
            </Tooltip>
            <Tooltip title={isExpanded ? "收起侧栏" : "展开侧栏"} placement="right">
              <button onClick={() => setSidebarState({ isExpanded: !isExpanded })}
                className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors">
                {isExpanded ? <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" /> : <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />}
              </button>
            </Tooltip>
          </>
        ) : (
          <div className="flex items-center gap-2 w-full">
            <Link to="/settings" onClick={() => setHeader({ title: "Settings", breadcrumbs: [{ name: "Settings", href: "/settings", current: true }] })}
              className="group flex flex-1 gap-x-3 rounded-md p-2 text-sm text-primary hover:text-accent hover:bg-secondary">
              <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
              {showFull && "设置"}
            </Link>
            <button onClick={() => setSidebarState({ isExpanded: !isExpanded })}
              className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors">
              {isExpanded ? <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" /> : <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
