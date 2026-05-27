import React, { createContext, useState, useEffect } from "react";

interface AppContextType {
  darkMode: string;
  setDarkMode: (mode: string) => void;
}

export const appContext = createContext<AppContextType>({ darkMode: "light", setDarkMode: () => {} });

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("darkMode") || "light";
    return "light";
  });

  useEffect(() => { localStorage.setItem("darkMode", darkMode); }, [darkMode]);

  return <appContext.Provider value={{ darkMode, setDarkMode }}>{children}</appContext.Provider>;
};
