import { useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useConfigStore, useWorkspaceStore } from "../hooks/store";
import { Tooltip } from "antd";
import { Settings, PanelLeftClose, PanelLeftOpen } from "lucide-react";
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

  const currentWorkspaceId = location.pathname.startsWith("/chat/")
    ? location.pathname.split("/chat/")[1] : null;

  useEffect(() => {
    fetch("/api/workspaces").then(r => r.json()).then(d => setWorkspaces(d)).catch(() => {});
  }, []);

  const handleWorkspaceClick = (id: string, title: string) => {
    setHeader({ title, breadcrumbs: [{ name: title, href: `/chat/${id}`, current: true }] });
    navigate(`/chat/${id}`);
  };

  return (
    <div className={classNames(
      "flex grow z-50 flex-col gap-y-5 overflow-y-auto scroll border-r border-secondary bg-primary",
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

      {/* Workspace list */}
      {showFull ? (
        <div className="flex-1 -mx-2">
          <div className="text-xs font-semibold text-secondary uppercase px-2 mb-1 tracking-wider">课题</div>
          <div className="space-y-0.5">
            {workspaces.map((w) => {
              const isActive = w.id === currentWorkspaceId;
              return (
                <div key={w.id} className="relative">
                  {isActive && <div className="bg-accent absolute top-1 left-0.5 z-50 h-8 w-1 bg-opacity-80 rounded" />}
                  <button onClick={() => handleWorkspaceClick(w.id, w.title)}
                    className={classNames(
                      "w-full text-left ml-1 flex gap-x-3 rounded-md mr-2 p-2 text-sm font-medium",
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
