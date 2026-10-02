import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import { NotificationProvider } from "./components/NotificationProvider";
import { RefreshProvider } from "./components/RefreshProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";

// The inventory list is the start page and ships in the main bundle; every
// other page (charts, barcode decoder, markdown, Picnic) loads on first visit.
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ScanPage = lazy(() => import("./pages/ScanPage"));
const RecipesPage = lazy(() => import("./pages/RecipesPage"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const PersonsPage = lazy(() => import("./pages/PersonsPage"));
const PicnicLoginPage = lazy(() => import("./pages/PicnicLoginPage"));
const PicnicStorePage = lazy(() => import("./pages/PicnicStorePage"));

// The iPad scan station (pages/ScanStationPage.tsx) is disabled for now:
// no route, no nav entry. Re-add both to bring it back.

const PageFallback = () => (
  <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
    <CircularProgress />
  </Box>
);

const App = () => {
  // Detect HA ingress base path from document.baseURI
  const basePath = document.baseURI
    ? new URL(document.baseURI).pathname.replace(/\/$/, "")
    : "";

  return (
    <BrowserRouter basename={basePath}>
      <NotificationProvider>
        <RefreshProvider>
          <Navbar />
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<InventoryPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/scan" element={<ScanPage />} />
              <Route path="/recipes" element={<RecipesPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/persons" element={<PersonsPage />} />
              <Route path="/picnic-login" element={<PicnicLoginPage />} />
              <Route path="/picnic" element={<PicnicStorePage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </RefreshProvider>
      </NotificationProvider>
    </BrowserRouter>
  );
};

export default App;
