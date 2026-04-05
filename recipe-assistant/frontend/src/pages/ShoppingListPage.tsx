import { useState } from "react";
import {
  Box,
  Button,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import { useShoppingList, usePicnicSearch } from "../hooks/usePicnic";
import type { CartSyncResponse } from "../types";

export default function ShoppingListPage() {
  const { items, remove, update, sync, add } = useShoppingList();
  const { results, search } = usePicnicSearch();
  const [searchQuery, setSearchQuery] = useState("");
  const [syncResult, setSyncResult] = useState<CartSyncResponse | null>(null);

  const handleSync = async () => {
    const result = await sync();
    setSyncResult(result);
  };

  const handleAddFromSearch = async (picnic_id: string, name: string) => {
    await add({ picnic_id, name, quantity: 1 });
    setSearchQuery("");
    search("");
  };

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Einkaufsliste
      </Typography>

      {/* Search card */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <TextField
          fullWidth
          size="small"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            search(e.target.value);
          }}
          placeholder="Picnic-Produkt suchen..."
        />
        {results.length > 0 && (
          <List dense disablePadding sx={{ mt: 1, maxHeight: 240, overflowY: "auto" }}>
            {results.map((r) => (
              <ListItemButton
                key={r.picnic_id}
                onClick={() => handleAddFromSearch(r.picnic_id, r.name)}
              >
                <ListItemText
                  primary={r.name}
                  secondary={r.unit_quantity ?? undefined}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </Paper>

      {/* Shopping list */}
      <List disablePadding>
        {items.map((item) => (
          <ListItem
            key={item.id}
            sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, mb: 1 }}
            secondaryAction={
              <IconButton edge="end" color="error" onClick={() => remove(item.id)}>
                <DeleteIcon />
              </IconButton>
            }
          >
            {/* Status dot */}
            <Box
              component="span"
              sx={{
                color: item.picnic_status === "mapped" ? "success.main" : "error.main",
                fontSize: "1.5em",
                mr: 1,
                lineHeight: 1,
                flexShrink: 0,
              }}
              title={item.picnic_status === "mapped" ? "bei Picnic verfügbar" : "nicht bei Picnic verfügbar"}
            >
              ●
            </Box>

            <ListItemText
              sx={{ mr: 1 }}
              primary={item.name}
              secondary={
                item.picnic_status === "mapped" && item.picnic_name && item.picnic_name !== item.name
                  ? `→ ${item.picnic_name}`
                  : item.picnic_status === "unavailable"
                  ? (
                    <Typography component="span" variant="caption" color="error.main">
                      nicht bei Picnic verfügbar
                    </Typography>
                  )
                  : undefined
              }
            />

            <TextField
              type="number"
              size="small"
              sx={{ width: 80, flexShrink: 0 }}
              inputProps={{ min: 1 }}
              value={item.quantity}
              onChange={(e) => update(item.id, { quantity: Number(e.target.value) })}
            />
          </ListItem>
        ))}
      </List>

      {items.length > 0 && (
        <Button
          variant="contained"
          color="success"
          sx={{ mt: 2 }}
          onClick={handleSync}
        >
          In Picnic-Cart übertragen
        </Button>
      )}

      {syncResult && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Typography>Hinzugefügt: {syncResult.added_count}</Typography>
          <Typography>Übersprungen (nicht bei Picnic verfügbar): {syncResult.skipped_count}</Typography>
          <Typography>Fehlgeschlagen: {syncResult.failed_count}</Typography>
          {syncResult.failed_count > 0 && (
            <List dense disablePadding sx={{ mt: 1 }}>
              {syncResult.results
                .filter((r) => r.status === "failed")
                .map((r) => (
                  <ListItem key={r.shopping_list_id} disablePadding>
                    <ListItemText
                      primary={`Item #${r.shopping_list_id}: ${r.failure_reason}`}
                      primaryTypographyProps={{ color: "error.main", variant: "body2" }}
                    />
                  </ListItem>
                ))}
            </List>
          )}
        </Paper>
      )}
    </Paper>
  );
}
