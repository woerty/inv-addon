import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, CircularProgress, TextField, Typography } from "@mui/material";
import { usePicnicCategories } from "../../../hooks/usePicnicCategories";
import { usePicnicSearch } from "../../../hooks/usePicnic";
import CategoryChips from "./CategoryChips";
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
  const { categories, loading: catLoading } = usePicnicCategories();
  const { results: searchResults, loading: searchLoading, search } = usePicnicSearch();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSubCategory, setSelectedSubCategory] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const isSearching = query.length >= 2;

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
    clearTimeout(timerRef.current);
    if (value.length >= 2) {
      timerRef.current = setTimeout(() => search(value), DEBOUNCE_MS);
    }
  }, [search]);

  useEffect(() => { setSelectedSubCategory(null); }, [selectedCategory]);

  const activeCategory = useMemo(
    () => categories.find(c => c.id === selectedCategory),
    [categories, selectedCategory],
  );

  const activeSubCategory = useMemo(
    () => activeCategory?.children.find(s => s.id === selectedSubCategory),
    [activeCategory, selectedSubCategory],
  );

  const products = useMemo(() => {
    if (isSearching) return searchResults;
    if (activeSubCategory) return activeSubCategory.items;
    if (activeCategory) return activeCategory.children.flatMap(s => s.items);
    return [];
  }, [isSearching, searchResults, activeSubCategory, activeCategory]);

  const loading = isSearching ? searchLoading : catLoading;

  return (
    <Box>
      <TextField
        fullWidth size="small" placeholder="Produkt suchen..."
        value={query} onChange={e => handleQueryChange(e.target.value)} sx={{ mb: 2 }}
      />
      {!isSearching && (
        <>
          <CategoryChips items={categories} selected={selectedCategory} onSelect={setSelectedCategory} />
          {activeCategory && activeCategory.children.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <CategoryChips items={activeCategory.children} selected={selectedSubCategory} onSelect={setSelectedSubCategory} />
            </Box>
          )}
        </>
      )}
      <Box sx={{ mt: 2 }}>
        {loading ? (
          <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
        ) : products.length === 0 ? (
          <Typography color="text.secondary" textAlign="center" py={4}>
            {isSearching ? "Keine Ergebnisse" : selectedCategory ? "Keine Produkte in dieser Kategorie" : "Wähle eine Kategorie oder suche nach Produkten"}
          </Typography>
        ) : (
          <ProductGrid
            items={products} cartQuantities={cartQuantities} orderQuantities={orderQuantities}
            inventoryQuantities={inventoryQuantities} subscribedIds={subscribedIds} onProductClick={onProductClick}
          />
        )}
      </Box>
    </Box>
  );
}
