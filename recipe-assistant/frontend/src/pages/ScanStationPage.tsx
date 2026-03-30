import { useState } from "react";
import { Box, Button, Paper, Typography } from "@mui/material";
import { useZxing } from "react-zxing";
import { useNavigate } from "react-router-dom";
import { useScanner } from "../hooks/useScanner";
import { addItemByBarcode, removeItemByBarcode } from "../api/client";

type Mode = "add" | "remove";

interface FeedbackState {
  message: string;
  type: "success" | "error";
}

const ScanStationPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("remove");
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);

  const processBarcode = async (barcode: string) => {
    try {
      const result =
        mode === "add"
          ? await addItemByBarcode(barcode)
          : await removeItemByBarcode(barcode);
      setFeedback({ message: result.message, type: "success" });
    } catch (e) {
      setFeedback({
        message: e instanceof Error ? e.message : "Fehler",
        type: "error",
      });
    }
  };

  const { handleDecode } = useScanner({ onScan: processBarcode, cooldownMs: 2000 });
  const { ref } = useZxing({
    onDecodeResult: (result) => handleDecode(result.getText()),
  });

  return (
    <Box
      sx={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#121212",
        color: "white",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2,
          py: 1,
          bgcolor: "#1e1e1e",
        }}
      >
        <Button
          variant="text"
          sx={{ color: "white", fontSize: "1.2rem" }}
          onClick={() => navigate("/")}
        >
          &larr; Menü
        </Button>
        <Typography variant="h5" fontWeight="bold">
          Scan-Station
        </Typography>
        <Box sx={{ width: 80 }} />
      </Box>

      {/* Camera */}
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", p: 2 }}>
        <video
          ref={ref}
          style={{
            width: "100%",
            maxHeight: "100%",
            borderRadius: 12,
            objectFit: "cover",
          }}
        />
      </Box>

      {/* Mode Toggle */}
      <Box sx={{ display: "flex", gap: 1, px: 2, pb: 1 }}>
        <Button
          fullWidth
          variant={mode === "add" ? "contained" : "outlined"}
          onClick={() => setMode("add")}
          sx={{
            py: 2,
            fontSize: "1.3rem",
            fontWeight: "bold",
            bgcolor: mode === "add" ? "#2e7d32" : "transparent",
            borderColor: "#2e7d32",
            color: mode === "add" ? "white" : "#2e7d32",
            "&:hover": { bgcolor: mode === "add" ? "#1b5e20" : "rgba(46,125,50,0.1)" },
          }}
        >
          EINTRAGEN
        </Button>
        <Button
          fullWidth
          variant={mode === "remove" ? "contained" : "outlined"}
          onClick={() => setMode("remove")}
          sx={{
            py: 2,
            fontSize: "1.3rem",
            fontWeight: "bold",
            bgcolor: mode === "remove" ? "#d32f2f" : "transparent",
            borderColor: "#d32f2f",
            color: mode === "remove" ? "white" : "#d32f2f",
            "&:hover": { bgcolor: mode === "remove" ? "#b71c1c" : "rgba(211,47,47,0.1)" },
          }}
        >
          AUSTRAGEN
        </Button>
      </Box>

      {/* Feedback */}
      <Paper
        sx={{
          m: 2,
          mt: 0,
          p: 2,
          textAlign: "center",
          bgcolor: feedback
            ? feedback.type === "success"
              ? "#1b5e20"
              : "#b71c1c"
            : "#333",
          color: "white",
          minHeight: 60,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 2,
        }}
      >
        <Typography variant="h6" fontWeight="bold">
          {feedback?.message ?? "Bereit zum Scannen..."}
        </Typography>
      </Paper>
    </Box>
  );
};

export default ScanStationPage;
