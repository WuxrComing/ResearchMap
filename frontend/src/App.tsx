import { BrowserRouter } from "react-router-dom";
import AppProvider from "./hooks/provider";
import AppLayout from "./components/layout";

function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AppLayout />
      </AppProvider>
    </BrowserRouter>
  );
}

export default App;
