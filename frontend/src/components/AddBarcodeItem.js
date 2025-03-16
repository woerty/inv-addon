import React, { useState, useEffect, useCallback } from "react";
import {
  TextField,
  Button,
  Paper,
  Typography,
  MenuItem,
  Select,
  RadioGroup,
  FormControlLabel,
  Radio,
  FormControl,
  FormLabel,
} from "@mui/material";

const AddBarcodeItem = ({ showNotification }) => {
  const [barcode, setBarcode] = useState("");
  const [storageLocations, setStorageLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [mode, setMode] = useState("add"); // "add" für Hinzufügen, "remove" für Entfernen

  const fetchStorageLocations = useCallback(() => {
    fetch("http://localhost:5000/storage-locations")
      .then((response) => response.json())
      .then((data) => setStorageLocations(data))
      .catch(() => showNotification("Fehler beim Abrufen der Lagerorte", "error"));
  }, [showNotification]);

  useEffect(() => {
    fetchStorageLocations();
  }, [fetchStorageLocations]);

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!barcode.trim()) {
      showNotification("Bitte einen Barcode eingeben", "warning");
      return;
    }

    if (mode === "add") {
      const storageLocation = newLocation.trim() ? newLocation.trim() : selectedLocation;

      if (newLocation.trim()) {
        fetch("http://localhost:5000/storage-locations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ location_name: newLocation.trim() }),
        })
          .then((response) => response.json())
          .then(() => fetchStorageLocations())
          .catch(() => showNotification("Fehler beim Speichern des neuen Lagerorts", "error"));
      }

      fetch("http://localhost:5000/inventory/barcode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode, storage_location: storageLocation }),
      })
        .then((response) => {
          if (!response.ok) throw new Error("Produkt nicht gefunden");
          return response.json();
        })
        .then((data) => {
          showNotification(data.message, "success");
          setBarcode("");
          setNewLocation("");
        })
        .catch((error) => showNotification("Fehler beim Hinzufügen: " + error.message, "error"));
    } else if (mode === "remove") {
      fetch("http://localhost:5000/inventory/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode }),
      })
        .then((response) => {
          if (!response.ok) throw new Error("Produkt nicht gefunden oder Fehler beim Entfernen");
          return response.json();
        })
        .then((data) => {
          showNotification(data.message, "success");
          setBarcode("");
        })
        .catch((error) => showNotification("Fehler beim Entfernen: " + error.message, "error"));
    }
  };

  return (
    <Paper sx={{ padding: 2 }}>
      <Typography variant="h4" gutterBottom>
        Inventar verwalten
      </Typography>

      <FormControl component="fieldset" sx={{ mb: 2 }}>
        <FormLabel component="legend">Modus</FormLabel>
        <RadioGroup
          row
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <FormControlLabel value="add" control={<Radio />} label="Hinzufügen" />
          <FormControlLabel value="remove" control={<Radio />} label="Entfernen" />
        </RadioGroup>
      </FormControl>

      <form onSubmit={handleSubmit}>
        <TextField
          label="Barcode"
          variant="outlined"
          fullWidth
          margin="normal"
          value={barcode}
          onChange={(e) => setBarcode(e.target.value)}
          required
        />

        {mode === "add" && (
          <>
            <Select
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              displayEmpty
              fullWidth
              sx={{ marginBottom: 2 }}
            >
              <MenuItem value="">Lagerort auswählen...</MenuItem>
              {storageLocations.map((location) => (
                <MenuItem key={location.id} value={location.location_name}>
                  {location.location_name}
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
          </>
        )}

        <Button type="submit" variant="contained" color={mode === "add" ? "primary" : "secondary"} fullWidth>
          {mode === "add" ? "Hinzufügen" : "Entfernen"}
        </Button>
      </form>
    </Paper>
  );
};

export default AddBarcodeItem;
