import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";
import ScanPage from "./pages/ScanPage";
import ScanStationPage from "./pages/ScanStationPage";
import RecipesPage from "./pages/RecipesPage";
import ChatPage from "./pages/ChatPage";
import PersonsPage from "./pages/PersonsPage";
import PicnicImportPage from "./pages/PicnicImportPage";
import PicnicLoginPage from "./pages/PicnicLoginPage";
import ShoppingListPage from "./pages/ShoppingListPage";
import TrackedProductsPage from "./pages/TrackedProductsPage";
import PicnicStorePage from "./pages/PicnicStorePage";

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
        <Route path="/picnic-import" element={<PicnicImportPage />} />
        <Route path="/picnic-login" element={<PicnicLoginPage />} />
        <Route path="/shopping-list" element={<ShoppingListPage />} />
        <Route path="/tracked-products" element={<TrackedProductsPage />} />
        <Route path="/picnic-store" element={<PicnicStorePage />} />
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
