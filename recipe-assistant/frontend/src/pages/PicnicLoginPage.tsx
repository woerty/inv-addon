import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { usePicnicLogin, usePicnicStatus } from "../hooks/usePicnic";

export default function PicnicLoginPage() {
  const { phase, error, start, sendCode, verify, reset } = usePicnicLogin();
  const { refetch } = usePicnicStatus();
  const [code, setCode] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (phase === "success") {
      refetch();
      const t = setTimeout(() => navigate("/picnic-import"), 1500);
      return () => clearTimeout(t);
    }
  }, [phase, navigate, refetch]);

  const handleReset = () => {
    setCode("");
    reset();
  };

  return (
    <Paper sx={{ p: 2, m: 2, maxWidth: 500, mx: "auto" }}>
      <Typography variant="h4" gutterBottom>
        Picnic Login
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Picnic benötigt eine Zwei-Faktor-Authentifizierung. Klicke auf "Login
        starten", um den Code anzufordern.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {phase === "idle" && (
        <Button variant="contained" onClick={start}>
          Login starten
        </Button>
      )}

      {phase === "starting" && (
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography>Login wird gestartet...</Typography>
        </Box>
      )}

      {phase === "awaiting_2fa" && (
        <Box>
          <Typography variant="h6" gutterBottom>
            Zwei-Faktor-Code anfordern
          </Typography>
          <Stack direction="row" spacing={2}>
            <Button variant="contained" onClick={() => sendCode("SMS")}>
              Per SMS senden
            </Button>
            <Button variant="outlined" onClick={() => sendCode("EMAIL")}>
              Per E-Mail senden
            </Button>
          </Stack>
        </Box>
      )}

      {phase === "sending_code" && (
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography>Code wird gesendet...</Typography>
        </Box>
      )}

      {phase === "awaiting_code" && (
        <Box>
          <TextField
            label="Bestätigungscode"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            fullWidth
            sx={{ mb: 2 }}
            inputProps={{
              inputMode: "numeric",
              autoComplete: "one-time-code",
            }}
          />
          <Stack direction="row" spacing={2}>
            <Button
              variant="contained"
              onClick={() => verify(code)}
              disabled={!code.trim()}
            >
              Überprüfen
            </Button>
            <Button variant="outlined" onClick={handleReset}>
              Neuen Code anfordern
            </Button>
          </Stack>
        </Box>
      )}

      {phase === "verifying" && (
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography>Code wird überprüft...</Typography>
        </Box>
      )}

      {phase === "success" && (
        <Alert severity="success">Erfolgreich eingeloggt!</Alert>
      )}
    </Paper>
  );
}
