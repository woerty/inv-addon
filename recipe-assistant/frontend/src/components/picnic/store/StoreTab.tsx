import { useCallback, useRef, useState } from "react";
import { Box, CircularProgress, TextField, Typography } from "@mui/material";
import { usePicnicSearch } from "../../../hooks/usePicnic";
import ProductGrid from "./ProductGrid";

const DEBOUNCE_MS = 400;

interface StoreTabProps {
  cartQuantities: Record<string, number>;
  orderQuantities: Record<string, number>;
  inventoryQuantities: Record<string, number>;
  subscribedIds: Set<string>;
  onProductClick: (picnicId: string) => void;
}

export default function StoreTab({
  cartQuantities, orderQuantities, inventoryQuantities, subscribedIds, onProductClick,
}: StoreTabProps) {
  const { results: searchResults, loading: searchLoading, search } = usePicnicSearch();
  const [query, setQuery] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const isSearching = query.length >= 2;

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
    clearTimeout(timerRef.current);
    if (value.length >= 2) {
      timerRef.current = setTimeout(() => search(value), DEBOUNCE_MS);
    }
  }, [search]);

  return (
    <Box>
      <TextField
        fullWidth size="small" placeholder="Produkt suchen..."
        value={query} onChange={e => handleQueryChange(e.target.value)} sx={{ mb: 2 }}
      />

      {isSearching ? (
        searchLoading ? (
          <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
        ) : searchResults.length === 0 ? (
          <Typography color="text.secondary" textAlign="center" py={4}>
            Keine Ergebnisse
          </Typography>
        ) : (
          <ProductGrid
            items={searchResults}
            cartQuantities={cartQuantities}
            orderQuantities={orderQuantities}
            inventoryQuantities={inventoryQuantities}
            subscribedIds={subscribedIds}
            onProductClick={onProductClick}
          />
        )
      ) : (
        <Typography color="text.secondary" textAlign="center" py={4}>
          Suche nach Produkten um den Store zu durchstöbern
        </Typography>
      )}
    </Box>
  );
}
