import { Box, List, ListItemButton, ListItemText, Typography } from "@mui/material";
import type { MatchSuggestion } from "../../types";

interface Props {
  suggestions: MatchSuggestion[];
  selectedBarcode: string | null;
  onSelect: (barcode: string | null) => void;
}

export function MatchCandidateList({ suggestions, selectedBarcode, onSelect }: Props) {
  if (suggestions.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Kein Vorschlag
      </Typography>
    );
  }

  return (
    <Box>
      <List dense disablePadding>
        {suggestions.map((s) => {
          const isSelected = s.inventory_barcode === selectedBarcode;
          const tier =
            s.score >= 92 ? "confident" : s.score >= 75 ? "uncertain" : "weak";
          const scoreColor =
            tier === "confident"
              ? "success.main"
              : tier === "uncertain"
              ? "warning.main"
              : "text.secondary";

          return (
            <ListItemButton
              key={s.inventory_barcode}
              selected={isSelected}
              onClick={() => onSelect(isSelected ? null : s.inventory_barcode)}
              sx={{ borderRadius: 1, mb: 0.5 }}
            >
              <ListItemText
                primary={s.inventory_name}
                secondary={
                  <Typography
                    component="span"
                    variant="caption"
                    color={scoreColor}
                  >
                    {Math.round(s.score)} — {s.reason}
                  </Typography>
                }
              />
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}
