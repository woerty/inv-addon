import { useCallback, useEffect, useRef, useState } from "react";
import { Box, CircularProgress, TextField, Typography } from "@mui/material";
import { usePicnicSearch } from "../../../hooks/usePicnic";
import { getRecentProducts } from "../../../api/client";
import ProductCard from "./ProductCard";
import ProductGrid from "./ProductGrid";
import type { PicnicSearchResult } from "../../../types";

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
  const [recentProducts, setRecentProducts] = useState<PicnicSearchResult[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const isSearching = query.length >= 2;

  useEffect(() => {
    getRecentProducts()
      .then((data) => setRecentProducts(data.products))
      .catch(() => {})
      .finally(() => setRecentLoading(false));
  }, []);

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
        <Box>
          {searchLoading ? (
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
          )}
        </Box>
      ) : (
        <Box>
          <Typography variant="h6" gutterBottom>Zuletzt bestellt</Typography>
          {recentLoading ? (
            <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
          ) : recentProducts.length === 0 ? (
            <Typography color="text.secondary" py={2}>
              Noch keine Bestellungen — nutze die Suche oben um Produkte zu finden.
            </Typography>
          ) : (
            <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 2 }}>
              {recentProducts.map(p => (
                <Box key={p.picnic_id} sx={{ minWidth: 160, maxWidth: 180, flexShrink: 0 }}>
                  <ProductCard
                    picnicId={p.picnic_id}
                    name={p.name}
                    unitQuantity={p.unit_quantity}
                    imageId={p.image_id}
                    priceCents={p.price_cents}
                    inCart={cartQuantities[p.picnic_id] ?? 0}
                    onOrder={orderQuantities[p.picnic_id] ?? 0}
                    inInventory={inventoryQuantities[p.picnic_id] ?? 0}
                    isSubscribed={subscribedIds.has(p.picnic_id)}
                    onClick={onProductClick}
                  />
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
