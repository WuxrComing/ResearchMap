import React from "react";
import { MoonIcon, SunIcon } from "@heroicons/react/24/outline";
import { Menu as MenuIcon } from "lucide-react";
import { appContext } from "../hooks/provider";
import { useConfigStore } from "../hooks/store";
import { Link } from "react-router-dom";

type ContentHeaderProps = {
  onMobileMenuToggle: () => void;
  isMobileMenuOpen: boolean;
};

const ContentHeader = ({ onMobileMenuToggle }: ContentHeaderProps) => {
  const { darkMode, setDarkMode } = React.useContext(appContext);
  const { header } = useConfigStore();
  const { title, breadcrumbs } = header;

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
