import { useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Typography,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import type { ImportCandidate, ImportDecision } from "../../types";
import { MatchCandidateList } from "./MatchCandidateList";

interface Props {
  candidate: ImportCandidate;
  storageLocations: string[];
  onChange: (decision: ImportDecision) => void;
}

export function ReviewCard({ candidate, storageLocations, onChange }: Props) {
  const confident = candidate.best_confidence >= 92;
  const initialAction = confident ? "match_existing" : "skip";
  const initialTarget = confident ? (candidate.match_suggestions[0]?.inventory_barcode ?? null) : null;

  const [action, setAction] = useState<ImportDecision["action"]>(initialAction);
  const [targetBarcode, setTargetBarcode] = useState<string | null>(initialTarget);
  const [storageLocation, setStorageLocation] = useState<string>(storageLocations[0] ?? "");

  const update = (patch: Partial<ImportDecision>) => {
    const next: ImportDecision = {
      picnic_id: candidate.picnic_id,
      action,
      target_barcode: targetBarcode,
      storage_location: action === "create_new" ? storageLocation : null,
      ...patch,
    };
    onChange(next);
  };

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        {/* Product info row */}
        <Box sx={{ display: "flex", gap: 2, mb: 2 }}>
          {candidate.picnic_image_id && (
            <Box
              component="img"
              src={`https://storefront-prod.de.picnicinternational.com/static/images/${candidate.picnic_image_id}/tile-small.png`}
              alt=""
              sx={{ width: 64, height: 64, objectFit: "contain", flexShrink: 0 }}
            />
          )}
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" fontWeight="bold">
              {candidate.picnic_name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {candidate.picnic_unit_quantity} × {candidate.ordered_quantity}
            </Typography>
          </Box>
        </Box>

        {/* Action selector */}
        <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
          <Button
            variant={action === "match_existing" ? "contained" : "outlined"}
            size="small"
            onClick={() => {
              setAction("match_existing");
              update({ action: "match_existing" });
            }}
          >
            Zuordnen
          </Button>
          <Button
            variant={action === "create_new" ? "contained" : "outlined"}
            size="small"
            onClick={() => {
              setAction("create_new");
              update({ action: "create_new" });
            }}
          >
            Neu anlegen
          </Button>
          <Button
            variant={action === "skip" ? "contained" : "outlined"}
            size="small"
            onClick={() => {
              setAction("skip");
              update({ action: "skip" });
            }}
          >
            Überspringen
          </Button>
        </Box>

        {/* Match candidates */}
        {action === "match_existing" && (
          <MatchCandidateList
            suggestions={candidate.match_suggestions}
            selectedBarcode={targetBarcode}
            onSelect={(b) => {
              setTargetBarcode(b);
              update({ target_barcode: b });
            }}
          />
        )}

        {/* Storage location for new item */}
        {action === "create_new" && (
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Lagerort</InputLabel>
            <Select
              value={storageLocation}
              label="Lagerort"
              onChange={(e: SelectChangeEvent) => {
                setStorageLocation(e.target.value);
                update({ storage_location: e.target.value });
              }}
            >
              {storageLocations.map((loc) => (
                <MenuItem key={loc} value={loc}>
                  {loc}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </CardContent>
    </Card>
  );
}
