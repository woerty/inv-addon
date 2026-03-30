import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";
import ScanPage from "./pages/ScanPage";
import ScanStationPage from "./pages/ScanStationPage";
import RecipesPage from "./pages/RecipesPage";
import ChatPage from "./pages/ChatPage";

const AppContent = () => {
  const location = useLocation();
  const hideNavbar = location.pathname === "/scan-station";

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<InventoryPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/scan-station" element={<ScanStationPage />} />
        <Route path="/recipes" element={<RecipesPage />} />
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
    </>
  );
};

const App = () => (
  <BrowserRouter>
    <NotificationProvider>
      <AppContent />
    </NotificationProvider>
  </BrowserRouter>
);

export default App;
