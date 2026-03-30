import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";

const Placeholder = ({ name }: { name: string }) => (
  <div style={{ padding: 24 }}>{name} - Coming Soon</div>
);

const AppContent = () => {
  const location = useLocation();
  const hideNavbar = location.pathname === "/scan-station";

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<Placeholder name="Inventar" />} />
        <Route path="/scan" element={<Placeholder name="Scannen" />} />
        <Route path="/scan-station" element={<Placeholder name="Scan-Station" />} />
        <Route path="/recipes" element={<Placeholder name="Rezepte" />} />
        <Route path="/chat" element={<Placeholder name="Chat" />} />
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
