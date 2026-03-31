import { useEffect, useState } from "react";
import {
  Box,
  Button,
  FormControl,
  FormControlLabel,
  FormLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import { useZxing } from "react-zxing";
import { useScanner, useCameraSwitch } from "../hooks/useScanner";
import { useNotification } from "../components/NotificationProvider";
import { addItemByBarcode, removeItemByBarcode, getStorageLocations, createStorageLocation } from "../api/client";
import type { StorageLocation } from "../types";
import CameraswitchIcon from "@mui/icons-material/Cameraswitch";
import { IconButton } from "@mui/material";

const ScanPage = () => {
  const { notify } = useNotification();
  const [mode, setMode] = useState<"add" | "remove">("add");
  const [manualBarcode, setManualBarcode] = useState("");
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [selectedLocation, setSelectedLocation] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [expirationDate, setExpirationDate] = useState("");

  useEffect(() => {
    getStorageLocations().then(setLocations).catch(() => {});
  }, []);

  const processBarcode = async (barcode: string) => {
    try {
      if (mode === "add") {
        const location = newLocation.trim() || selectedLocation;
        if (newLocation.trim()) {
          await createStorageLocation(newLocation.trim());
          const updated = await getStorageLocations();
          setLocations(updated);
          setNewLocation("");
        }
        const result = await addItemByBarcode(barcode, location, expirationDate || undefined);
        notify(result.message, "success");
      } else {
        const result = await removeItemByBarcode(barcode);
        notify(result.message, "success");
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const { lastScanned, handleDecode } = useScanner({ onScan: processBarcode });
  const { facingMode, toggle: toggleCamera } = useCameraSwitch();
  const { ref } = useZxing({
    onDecodeResult: (result) => handleDecode(result.getText()),
    constraints: { video: { facingMode } },
  });

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualBarcode.trim()) return;
    processBarcode(manualBarcode.trim());
    setManualBarcode("");
  };

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Barcode Scanner
      </Typography>

      <FormControl component="fieldset" sx={{ mb: 2 }}>
        <FormLabel>Modus</FormLabel>
        <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value as "add" | "remove")}>
          <FormControlLabel value="add" control={<Radio />} label="Hinzufügen" />
          <FormControlLabel value="remove" control={<Radio />} label="Entfernen" />
        </RadioGroup>
      </FormControl>

      <Box sx={{ position: "relative" }}>
        <video ref={ref} style={{ width: "100%", maxHeight: 300, borderRadius: 8 }} />
        <IconButton
          onClick={toggleCamera}
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            bgcolor: "rgba(0,0,0,0.5)",
            color: "white",
            "&:hover": { bgcolor: "rgba(0,0,0,0.7)" },
          }}
        >
          <CameraswitchIcon />
        </IconButton>
      </Box>

      {lastScanned && (
        <Paper
          sx={{
            mt: 1,
            mb: 1,
            p: 1.5,
            bgcolor: "#e8f5e9",
            textAlign: "center",
          }}
        >
          <Typography variant="body1" fontWeight="bold">
            Gescannt: {lastScanned}
          </Typography>
        </Paper>
      )}

      <form onSubmit={handleManualSubmit}>
        <TextField
          label="Barcode manuell eingeben"
          variant="outlined"
          fullWidth
          margin="normal"
          value={manualBarcode}
          onChange={(e) => setManualBarcode(e.target.value)}
        />

        {mode === "add" && (
          <>
            <Select
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              displayEmpty
              fullWidth
              sx={{ mb: 2 }}
            >
              <MenuItem value="">Lagerort auswählen...</MenuItem>
              {locations.map((loc) => (
                <MenuItem key={loc.id} value={loc.name}>
                  {loc.name}
                </MenuItem>
              ))}
            </Select>

            <TextField
              label="Neuer Lagerplatz (optional)"
              variant="outlined"
              fullWidth
              margin="normal"
              value={newLocation}
              onChange={(e) => setNewLocation(e.target.value)}
            />

            <TextField
              label="Ablaufdatum (optional)"
              type="date"
              fullWidth
              margin="normal"
              slotProps={{ inputLabel: { shrink: true } }}
              value={expirationDate}
              onChange={(e) => setExpirationDate(e.target.value)}
            />
          </>
        )}

        <Button
          type="submit"
          variant="contained"
          color={mode === "add" ? "primary" : "secondary"}
          fullWidth
          sx={{ mt: 1 }}
        >
          {mode === "add" ? "Hinzufügen" : "Entfernen"}
        </Button>
      </form>
    </Paper>
  );
};

export default ScanPage;
