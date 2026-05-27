import React, { useState } from "react";
import { getLocalStorage, setLocalStorage } from "../components/utils/utils";

export interface AppContextType {
  darkMode: string;
  setDarkMode: any;
  user: null;
  setUser: any;
  logout: any;
  cookie_name: string;
}

export const appContext = React.createContext<AppContextType>({} as AppContextType);

const AppProvider = ({ children }: any) => {
  const storedValue = getLocalStorage("darkmode", false);
  const [darkMode, setDarkMode] = useState(
    storedValue === null ? "light" : storedValue === "dark" ? "dark" : "light"
  );

  const updateDarkMode = (darkMode: string) => {
    setDarkMode(darkMode);
    setLocalStorage("darkmode", darkMode, false);
  };

  return (
    <appContext.Provider
      value={{
        user: null,
        setUser: () => {},
        logout: () => {},
        cookie_name: "coral_app_cookie_",
        darkMode,
        setDarkMode: updateDarkMode,
      }}
    >
      {children}
    </appContext.Provider>
  );
};

export default AppProvider;
