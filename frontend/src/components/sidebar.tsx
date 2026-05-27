import { useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useConfigStore, useWorkspaceStore } from "../hooks/store";
import { Tooltip } from "antd";
import {
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import Icon from "./icons";

const classNames = (...classes: (string | undefined | boolean)[]) => {
  return classes.filter(Boolean).join(" ");
};

type SidebarProps = {
  link: string;
  meta?: { title: string; description: string };
  isMobile: boolean;
};

const Sidebar = ({ link: _link, meta, isMobile }: SidebarProps) => {
  const { sidebar, setHeader, setSidebarState } = useConfigStore();
  const { workspaces, setWorkspaces } = useWorkspaceStore();
  const { isExpanded } = sidebar;
  const navigate = useNavigate();
  const location = useLocation();
  const showFull = isMobile || isExpanded;

  const currentWorkspaceId = location.pathname.startsWith("/chat/")
    ? location.pathname.split("/chat/")[1]
    : null;

  useEffect(() => {
    fetch("/api/workspaces")
      .then((r) => r.json())
      .then((data) => setWorkspaces(data))
      .catch(() => {});
  }, []);

  const handleWorkspaceClick = (workspaceId: string, title: string) => {
    setHeader({
      title,
      breadcrumbs: [{ name: title, href: `/chat/${workspaceId}`, current: true }],
    });
    navigate(`/chat/${workspaceId}`);
  };

  const setNavigationHeader = (path: string) => {
    if (path === "/settings") {
      setHeader({
        title: "Settings",
        breadcrumbs: [{ name: "Settings", href: "/settings", current: true }],
      });
    } else if (path === "/" || path === "/workspaces") {
      setHeader({
        title: "课题管理",
        breadcrumbs: [{ name: "课题管理", href: "/workspaces", current: true }],
      });
    }
  };

  const sidebarWidth = useConfigStore((s) => s.sidebarWidth);

  return (
    <div
      className={classNames(
        "flex grow z-50 flex-col gap-y-5 overflow-y-auto border-r border-secondary bg-primary h-full",
        "transition-all duration-300 ease-in-out"
      )}
      style={{ width: showFull ? sidebarWidth : 64, paddingLeft: showFull ? 24 : 8, paddingRight: showFull ? 24 : 8 }}
    >
      {/* App Logo/Title */}
      <div className={`flex h-16 items-center ${showFull ? "gap-x-3" : "ml-2"}`}>
        <Link
          to="/"
          onClick={() => setNavigationHeader("/")}
          className="w-8 text-right text-accent hover:opacity-80 transition-opacity"
        >
          <Icon icon="app" size={8} />
        </Link>
        {showFull && (
          <div className="flex flex-col" style={{ minWidth: "200px" }}>
            <span className="text-base font-semibold text-primary">
              {meta?.title || "Research Map"}
            </span>
            <span className="text-xs text-secondary">
              {meta?.description || "科研思维导图 Agent"}
            </span>
          </div>
        )}
      </div>

      {/* Workspace List */}
      {showFull ? (
        <div className="flex-1 -mx-2">
          <div className="text-xs font-semibold text-secondary uppercase px-2 mb-1 tracking-wider">
            课题
          </div>
          <div className="space-y-0.5">
            {workspaces.map((w) => {
              const isActive = w.id === currentWorkspaceId;
              return (
                <div key={w.id} className="relative">
                  {isActive && (
                    <div className="bg-accent absolute top-1 left-0.5 z-50 h-8 w-1 bg-opacity-80 rounded" />
                  )}
                  <button
                    onClick={() => handleWorkspaceClick(w.id, w.title)}
                    className={classNames(
                      "w-full text-left ml-1 flex gap-x-3 rounded-md mr-2 p-2 text-sm font-medium",
                      isActive
                        ? "bg-secondary text-primary"
                        : "text-secondary hover:bg-tertiary hover:text-accent"
                    )}
                  >
                    <span
                      className="w-6 h-6 shrink-0 rounded flex items-center justify-center text-white text-xs font-bold"
                      style={{ backgroundColor: isActive ? "var(--color-bg-accent)" : "var(--color-text-secondary)" }}
                    >
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
                <button
                  onClick={() => handleWorkspaceClick(w.id, w.title)}
                  className={classNames(
                    "w-10 h-10 rounded-md flex items-center justify-center text-sm font-bold",
                    isActive
                      ? "bg-secondary text-accent"
                      : "text-secondary hover:bg-tertiary hover:text-accent"
                  )}
                >
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
            <Tooltip title="Settings" placement="right">
              <Link
                to="/settings"
                onClick={() =>
                  setHeader({
                    title: "Settings",
                    breadcrumbs: [{ name: "Settings", href: "/settings", current: true }],
                  })
                }
                className="group flex gap-x-3 rounded-md p-2 text-sm font-medium text-primary hover:text-accent hover:bg-secondary justify-center"
              >
                <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
              </Link>
            </Tooltip>
            <div className="hidden md:block">
              <Tooltip title={isExpanded ? "Close Sidebar" : "Open Sidebar"} placement="right">
                <button
                  onClick={() => setSidebarState({ isExpanded: !isExpanded })}
                  className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-opacity-50"
                >
                  {isExpanded ? (
                    <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" />
                  ) : (
                    <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />
                  )}
                </button>
              </Tooltip>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2 w-full">
            <Link
              to="/settings"
              onClick={() =>
                setHeader({
                  title: "Settings",
                  breadcrumbs: [{ name: "Settings", href: "/settings", current: true }],
                })
              }
              className="group flex flex-1 gap-x-3 rounded-md p-2 text-sm font-medium text-primary hover:text-accent hover:bg-secondary"
            >
              <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
              {showFull && "设置"}
            </Link>
            <div className="hidden md:block">
              <Tooltip title={`${isExpanded ? "Close Sidebar" : "Open Sidebar"}`} placement="right">
                <button
                  onClick={() => setSidebarState({ isExpanded: !isExpanded })}
                  className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-opacity-50"
                >
                  {isExpanded ? (
                    <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" />
                  ) : (
                    <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />
                  )}
                </button>
              </Tooltip>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
