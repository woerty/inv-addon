import React, { useState } from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { Snackbar, Alert } from "@mui/material";
import InventoryManager from "./components/InventoryManager";
import AddBarcodeItem from "./components/AddBarcodeItem";
import ChatAssistant from "./components/ChatAssistant";
import Assistant from "./components/Assistant";
import Navbar from "./components/Navbar";

function App() {
  const [notification, setNotification] = useState({
    open: false,
    message: "",
    severity: "info",
  });

  const showNotification = (message, severity = "info") => {
    setNotification({ open: true, message, severity });
  };

  const handleClose = () => {
    setNotification({ ...notification, open: false });
  };

  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/" element={<InventoryManager showNotification={showNotification} />} />
        <Route path="/add" element={<AddBarcodeItem showNotification={showNotification} />} />
        <Route path="/chat" element={<ChatAssistant />} />
        <Route path="/assistant" element={<Assistant />} />
      </Routes>

      <Snackbar
        open={notification.open}
        autoHideDuration={3000}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={handleClose} severity={notification.severity} sx={{ width: "100%" }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Router>
  );
}

export default App;
