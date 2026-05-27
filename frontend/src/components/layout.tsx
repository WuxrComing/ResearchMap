import * as React from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { Dialog } from "@headlessui/react";
import { X } from "lucide-react";
import { appContext } from "../hooks/provider";
import { useConfigStore } from "../hooks/store";
import Footer from "./footer";
import "antd/dist/reset.css";
import SideBar from "./sidebar";
import ContentHeader from "./contentheader";
import { ConfigProvider, theme } from "antd";
import WorkspacePage from "../pages/workspaces/WorkspacePage";
import ChatPage from "../pages/chat/ChatPage";
import SettingsPage from "../pages/settings/SettingsPage";

const classNames = (...classes: (string | undefined | boolean)[]) => {
  return classes.filter(Boolean).join(" ");
};

const SidebarResizeHandle: React.FC = () => {
  const dragging = React.useRef(false);
  const startX = React.useRef(0);
  const sidebarWidth = useConfigStore((s) => s.sidebarWidth);
  const setSidebarWidth = useConfigStore((s) => s.setSidebarWidth);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  React.useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      startX.current = e.clientX;
      setSidebarWidth(Math.max(200, Math.min(500, sidebarWidth + delta)));
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [sidebarWidth, setSidebarWidth]);

  return (
    <div
      className="fixed inset-y-0 z-40 w-1.5 cursor-col-resize hover:bg-accent/50 active:bg-accent transition-colors"
      style={{ left: sidebarWidth - 2 }}
      onMouseDown={onMouseDown}
    />
  );
};

const AppLayout = () => {
  const { darkMode } = React.useContext(appContext);
  const { sidebar, sidebarWidth } = useConfigStore();
  const { isExpanded } = sidebar;
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const location = useLocation();
  const link = location.pathname;

  const meta = { title: "Research Map", description: "科研思维导图 Agent" };

  React.useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [link]);

  React.useEffect(() => {
    document.getElementsByTagName("html")[0].className = `${
      darkMode === "dark" ? "dark bg-primary" : "light bg-primary"
    }`;
  }, [darkMode]);

  const contentOffset = isExpanded ? sidebarWidth : 64;

  return (
    <div className="min-h-screen flex">
      {/* Mobile menu */}
      <Dialog
        as="div"
        open={isMobileMenuOpen}
        onClose={() => setIsMobileMenuOpen(false)}
        className="relative z-50 md:hidden"
      >
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex">
          <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
            <div className="absolute right-0 top-0 flex w-16 justify-center pt-5">
              <button
                type="button"
                className="text-secondary"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                <span className="sr-only">Close sidebar</span>
                <X className="h-6 w-6" aria-hidden="true" />
              </button>
            </div>
            <SideBar link={link} meta={meta} isMobile={true} />
          </Dialog.Panel>
        </div>
      </Dialog>

      {/* Desktop sidebar */}
      <div className="hidden md:flex md:flex-col md:fixed md:inset-y-0">
        <SideBar link={link} meta={meta} isMobile={false} />
      </div>

      {/* Sidebar resize handle — only when expanded */}
      {isExpanded && <SidebarResizeHandle />}

      {/* Content area */}
      <div
        className={classNames(
          "flex-1 flex flex-col min-h-screen",
          "transition-all duration-300 ease-in-out",
        )}
        style={{ paddingLeft: contentOffset }}
      >
        <ContentHeader
          isMobileMenuOpen={isMobileMenuOpen}
          onMobileMenuToggle={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        />

        <ConfigProvider
          theme={{
            token: {
              borderRadius: 4,
              colorBgBase: darkMode === "dark" ? "#05080C" : "#ffffff",
            },
            algorithm:
              darkMode === "dark"
                ? theme.darkAlgorithm
                : theme.defaultAlgorithm,
          }}
        >
          <main className="flex-1 p-2 text-primary">
            <Routes>
              <Route path="/" element={<WorkspacePage />} />
              <Route path="/workspaces" element={<WorkspacePage />} />
              <Route path="/chat/:workspaceId" element={<ChatPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </ConfigProvider>

        <Footer />
      </div>
    </div>
  );
};

export default AppLayout;
