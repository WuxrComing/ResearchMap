import React from "react";
import { Link } from "react-router-dom";
import { useConfigStore } from "../hooks/store";
import { Tooltip } from "antd";
import {
  Settings,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import Icon from "./icons";

const navigation: { name: string; href: string; icon: React.ComponentType<{ className?: string }> }[] = [
  {
    name: "课题管理",
    href: "/workspaces",
    icon: ({ className }: { className?: string }) => (
      <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    ),
  },
  {
    name: "对话",
    href: "/chat",
    icon: MessagesSquare,
  },
];

const classNames = (...classes: (string | undefined | boolean)[]) => classes.filter(Boolean).join(" ");

type SidebarProps = { link: string; meta?: { title: string; description: string }; isMobile: boolean };

const Sidebar = ({ link, meta, isMobile }: SidebarProps) => {
  const { sidebar, setHeader, setSidebarState } = useConfigStore();
  const { isExpanded } = sidebar;
  const showFull = isMobile || isExpanded;

  const handleNavClick = (item: { name: string; href: string }) => {
    setHeader({ title: item.name, breadcrumbs: [{ name: item.name, href: item.href, current: true }] });
  };

  return (
    <div
      className={classNames(
        "flex grow z-50 flex-col gap-y-5 overflow-y-auto border-r border-secondary bg-primary",
        "transition-all duration-300 ease-in-out",
        showFull ? "w-72 px-6" : "w-16 px-2"
      )}
    >
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

      <nav className="flex flex-1 flex-col">
        <ul role="list" className="flex flex-1 flex-col gap-y-7">
          <li>
            <ul role="list" className={classNames("-mx-2 space-y-1", !showFull && "items-center")}>
              {navigation.map((item) => {
                const isActive = link.startsWith(item.href) && item.href !== "/";
                const IconComponent = item.icon;
                const navLink = (
                  <div className="relative">
                    {isActive && <div className="bg-accent absolute top-1 left-0.5 z-50 h-8 w-1 bg-opacity-80 rounded" />}
                    <Link
                      to={item.href}
                      onClick={() => handleNavClick(item)}
                      className={classNames(
                        "group ml-1 flex gap-x-3 rounded-md mr-2 p-2 text-sm font-medium",
                        !showFull && "justify-center",
                        isActive ? "bg-secondary text-primary" : "text-secondary hover:bg-tertiary hover:text-accent"
                      )}
                    >
                      <IconComponent className={classNames("h-6 w-6 shrink-0", isActive ? "text-accent" : "text-secondary group-hover:text-accent")} />
                      {showFull && item.name}
                    </Link>
                  </div>
                );
                return (
                  <li key={item.name}>
                    {!showFull && !isMobile ? <Tooltip title={item.name} placement="right">{navLink}</Tooltip> : navLink}
                  </li>
                );
              })}
            </ul>
          </li>

          <li className={classNames("mt-auto -mx-2 mb-4", !showFull && "flex flex-col items-center gap-1")}>
            {!showFull && !isMobile ? (
              <>
                <Tooltip title="设置" placement="right">
                  <Link to="/settings" className="group flex gap-x-3 rounded-md p-2 text-sm font-medium text-primary hover:text-accent hover:bg-secondary justify-center">
                    <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
                  </Link>
                </Tooltip>
                <Tooltip title={isExpanded ? "收起侧栏" : "展开侧栏"} placement="right">
                  <button
                    onClick={() => setSidebarState({ isExpanded: !isExpanded })}
                    className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors"
                  >
                    {isExpanded ? <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" /> : <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />}
                  </button>
                </Tooltip>
              </>
            ) : (
              <div className="flex items-center gap-2 w-full">
                <Link
                  to="/settings"
                  className="group flex flex-1 gap-x-3 rounded-md p-2 text-sm font-medium text-primary hover:text-accent hover:bg-secondary"
                >
                  <Settings className="h-6 w-6 shrink-0 text-secondary group-hover:text-accent" />
                  {showFull && "设置"}
                </Link>
                <button
                  onClick={() => setSidebarState({ isExpanded: !isExpanded })}
                  className="p-2 rounded-md hover:bg-secondary hover:text-accent text-secondary transition-colors"
                >
                  {isExpanded ? <PanelLeftClose strokeWidth={1.5} className="h-6 w-6" /> : <PanelLeftOpen strokeWidth={1.5} className="h-6 w-6" />}
                </button>
              </div>
            )}
          </li>
        </ul>
      </nav>
    </div>
  );
};

export default Sidebar;
