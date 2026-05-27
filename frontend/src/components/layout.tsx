import * as React from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { Dialog } from "@headlessui/react";
import { X } from "lucide-react";
import { appContext } from "../hooks/provider";
import { useConfigStore } from "../hooks/store";
import Footer from "./footer";
import Sidebar from "./sidebar";
import ContentHeader from "./contentheader";
import { ConfigProvider, theme } from "antd";
import WorkspacePage from "../pages/workspaces/WorkspacePage";
import ChatPage from "../pages/chat/ChatPage";
import SettingsPage from "../pages/settings/SettingsPage";

const classNames = (...classes: (string | undefined | boolean)[]) => classes.filter(Boolean).join(" ");

const Layout = () => {
  const { darkMode } = React.useContext(appContext);
  const { sidebar } = useConfigStore();
  const { isExpanded } = sidebar;
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => { setIsMobileMenuOpen(false); }, [location.pathname]);
  React.useEffect(() => {
    document.getElementsByTagName("html")[0].className = `${darkMode === "dark" ? "dark bg-primary" : "light bg-primary"}`;
  }, [darkMode]);

  const meta = { title: "Research Map", description: "科研思维导图 Agent" };

  return (
    <div className="min-h-screen flex">
      <Dialog as="div" open={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} className="relative z-50 md:hidden">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex">
          <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
            <div className="absolute right-0 top-0 flex w-16 justify-center pt-5">
              <button type="button" className="text-secondary" onClick={() => setIsMobileMenuOpen(false)}>
                <X className="h-6 w-6" />
              </button>
            </div>
            <Sidebar link={location.pathname} meta={meta} isMobile={true} />
          </Dialog.Panel>
        </div>
      </Dialog>

      <div className="hidden md:flex md:flex-col md:fixed md:inset-y-0">
        <Sidebar link={location.pathname} meta={meta} isMobile={false} />
      </div>

      <div className={classNames("flex-1 flex flex-col min-h-screen", "transition-all duration-300 ease-in-out", "md:pl-16", isExpanded ? "md:pl-72" : "md:pl-16")}>
        <ContentHeader isMobileMenuOpen={isMobileMenuOpen} onMobileMenuToggle={() => setIsMobileMenuOpen(!isMobileMenuOpen)} />

        <ConfigProvider theme={{
          token: { borderRadius: 4, colorBgBase: darkMode === "dark" ? "#05080C" : "#ffffff" },
          algorithm: darkMode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
        }}>
          <main className="flex-1 p-2 text-primary">
            <Routes>
              <Route path="/" element={<WorkspacePage />} />
              <Route path="/workspaces" element={<WorkspacePage />} />
              <Route path="/chat/:workspaceId" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </ConfigProvider>

        <Footer />
      </div>
    </div>
  );
};

export default Layout;
