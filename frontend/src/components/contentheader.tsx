import React, { useState } from "react";
import { MoonIcon, SunIcon } from "@heroicons/react/24/outline";
import { Menu as MenuIcon, Pencil } from "lucide-react";
import { appContext } from "../hooks/provider";
import { useConfigStore, useWorkspaceStore } from "../hooks/store";
import { Link, useLocation } from "react-router-dom";

type ContentHeaderProps = {
  onMobileMenuToggle: () => void;
  isMobileMenuOpen: boolean;
};

const ContentHeader = ({ onMobileMenuToggle, isMobileMenuOpen: _isMobileMenuOpen }: ContentHeaderProps) => {
  const { darkMode, setDarkMode } = React.useContext(appContext);
  const { header } = useConfigStore();
  const { workspaces, setWorkspaces } = useWorkspaceStore();
  const { title, breadcrumbs } = header;
  const location = useLocation();
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");

  const workspaceId = location.pathname.startsWith("/chat/")
    ? location.pathname.split("/chat/")[1] : null;
  const workspace = workspaceId ? workspaces.find(w => w.id === workspaceId) : null;

  const startEdit = () => {
    if (!workspace) return;
    setEditTitle(workspace.title);
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!workspace || !editTitle.trim()) { setEditing(false); return; }
    try {
      const res = await fetch(`/api/workspaces/${workspace.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: editTitle.trim(), description: workspace.description }),
      });
      if (res.ok) {
        const updated = await res.json();
        setWorkspaces(workspaces.map(w => w.id === updated.id ? updated : w));
      }
    } catch { /* */ }
    setEditing(false);
  };

  return (
    <div className="sticky top-0 z-40 bg-primary border-b border-secondary">
      <div className="flex h-16 items-center gap-x-4 px-4">
        <button
          onClick={onMobileMenuToggle}
          className="md:hidden p-2 rounded-md hover:bg-secondary text-secondary hover:text-accent transition-colors"
        >
          <MenuIcon className="h-6 w-6" />
        </button>

        <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
          <div className="flex flex-1 items-center min-w-0">
            {breadcrumbs && breadcrumbs.length > 0 ? (
              <nav aria-label="Breadcrumb" className="flex">
                <ol role="list" className="flex items-center space-x-4">
                  {breadcrumbs.map((page, index) => (
                    <li key={index}>
                      <div className="flex items-center">
                        {index > 0 && (
                          <svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true" className="size-5 shrink-0 text-secondary">
                            <path d="M5.555 17.776l8-16 .894.448-8 16-.894-.448z" />
                          </svg>
                        )}
                        <Link
                          to={page.href}
                          className={`text-sm font-medium ${index > 0 ? "ml-4" : ""} ${page.current ? "text-primary" : "text-secondary hover:text-accent"}`}
                        >
                          {page.name}
                        </Link>
                      </div>
                    </li>
                  ))}
                </ol>
              </nav>
            ) : (
              <h1 className="text-lg font-medium text-primary">{title}</h1>
            )}

            {/* Workspace info — shown when viewing a workspace */}
            {workspace && (
              <div className="ml-6 flex items-center gap-2 min-w-0">
                <div className="w-px h-6 bg-secondary/40" />
                {editing ? (
                  <input
                    className="text-sm font-medium bg-secondary/20 border border-accent rounded px-2 py-0.5 text-primary focus:outline-none w-40"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={saveEdit}
                    onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") setEditing(false); }}
                    autoFocus
                  />
                ) : (
                  <>
                    <span className="text-sm font-medium text-primary truncate">{workspace.title}</span>
                    <button
                      onClick={startEdit}
                      className="p-0.5 rounded hover:bg-secondary text-secondary hover:text-accent transition-colors shrink-0"
                      title="编辑课题名称"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
                {workspace.description && (
                  <span className="text-xs text-secondary truncate hidden sm:inline">{workspace.description}</span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-x-4 lg:gap-x-6 ml-auto">
            <button
              onClick={() => setDarkMode(darkMode === "dark" ? "light" : "dark")}
              className="text-secondary hover:text-primary"
            >
              {darkMode === "dark" ? <MoonIcon className="h-6 w-6" /> : <SunIcon className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContentHeader;
