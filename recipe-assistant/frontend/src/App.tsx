import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";
import ScanPage from "./pages/ScanPage";
import ScanStationPage from "./pages/ScanStationPage";
import RecipesPage from "./pages/RecipesPage";
import ChatPage from "./pages/ChatPage";
import PersonsPage from "./pages/PersonsPage";

const AppContent = () => {
  const location = useLocation();
  const hideNavbar = location.pathname.endsWith("/scan-station");

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<InventoryPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/scan-station" element={<ScanStationPage />} />
        <Route path="/recipes" element={<RecipesPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/persons" element={<PersonsPage />} />
      </Routes>
    </>
  );
};

const App = () => {
  // Detect HA ingress base path from document.baseURI
  const basePath = document.baseURI
    ? new URL(document.baseURI).pathname.replace(/\/$/, "")
    : "";

  return (
    <BrowserRouter basename={basePath}>
      <NotificationProvider>
        <AppContent />
      </NotificationProvider>
    </BrowserRouter>
  );
};

export default App;
