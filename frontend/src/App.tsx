import { BrowserRouter } from "react-router-dom";
import { AppProvider } from "./hooks/provider";
import Layout from "./components/layout";

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Layout />
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
