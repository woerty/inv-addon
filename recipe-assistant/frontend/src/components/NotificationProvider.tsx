import React, { createContext, useCallback, useContext, useState } from "react";
import { Alert, Snackbar } from "@mui/material";

type Severity = "success" | "error" | "warning" | "info";

interface NotificationContextType {
  notify: (message: string, severity?: Severity) => void;
}

const NotificationContext = createContext<NotificationContextType>({
  notify: () => {},
});

export const useNotification = () => useContext(NotificationContext);

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [severity, setSeverity] = useState<Severity>("info");

  const notify = useCallback((msg: string, sev: Severity = "info") => {
    setMessage(msg);
    setSeverity(sev);
    setOpen(true);
  }, []);

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      <Snackbar
        open={open}
        autoHideDuration={3000}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={() => setOpen(false)} severity={severity} sx={{ width: "100%" }}>
          {message}
        </Alert>
      </Snackbar>
    </NotificationContext.Provider>
  );
};
