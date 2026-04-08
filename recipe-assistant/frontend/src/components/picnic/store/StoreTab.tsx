import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box, Card, CardActionArea, CardContent, CardMedia, Chip,
  CircularProgress, TextField, Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid";
import { usePicnicCategories } from "../../../hooks/usePicnicCategories";
import { usePicnicSearch } from "../../../hooks/usePicnic";
import { getRecentProducts } from "../../../api/client";
import CategoryChips from "./CategoryChips";
import ProductCard from "./ProductCard";
import ProductGrid from "./ProductGrid";
import type { PicnicSearchResult } from "../../../types";

const DEBOUNCE_MS = 400;

const imgUrl = (imageId: string | null, size = "medium") =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/${size}.png`
    : undefined;

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
  const [recentProducts, setRecentProducts] = useState<PicnicSearchResult[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const isSearching = query.length >= 2;

  useEffect(() => {
    getRecentProducts()
      .then((data) => setRecentProducts(data.products))
      .catch(() => {});
  }, []);

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

  const showLanding = !isSearching && !selectedCategory;
  const loading = isSearching ? searchLoading : catLoading;

  return (
    <Box>
      <TextField
        fullWidth size="small" placeholder="Produkt suchen..."
        value={query} onChange={e => handleQueryChange(e.target.value)} sx={{ mb: 2 }}
      />

      {showLanding ? (
        <Box>
          {/* Zuletzt bestellt */}
          {recentProducts.length > 0 && (
            <>
              <Typography variant="h6" gutterBottom>Zuletzt bestellt</Typography>
              <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 2 }}>
                {recentProducts.map(p => (
                  <Box key={p.picnic_id} sx={{ minWidth: 160, maxWidth: 180 }}>
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
            </>
          )}

          {/* Kategorien als Kacheln */}
          {catLoading ? (
            <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
          ) : (
            <>
              <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>Kategorien</Typography>
              <Grid container spacing={2}>
                {categories.map(cat => (
                  <Grid item xs={6} sm={4} md={3} key={cat.id}>
                    <Card sx={{ cursor: "pointer" }} onClick={() => setSelectedCategory(cat.id)}>
                      <CardActionArea>
                        {cat.image_id && (
                          <CardMedia
                            component="img"
                            height="100"
                            image={imgUrl(cat.image_id)}
                            sx={{ objectFit: "contain", p: 1, bgcolor: "#fafafa" }}
                          />
                        )}
                        <CardContent sx={{ py: 1 }}>
                          <Typography variant="body2" fontWeight={500} textAlign="center">
                            {cat.name}
                          </Typography>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </Box>
      ) : !isSearching ? (
        /* Category selected -- chips + products with back button */
        <Box>
          <Chip
            label="\u2190 Alle Kategorien"
            onClick={() => setSelectedCategory(null)}
            sx={{ mb: 1 }}
          />
          {activeCategory && activeCategory.children.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <CategoryChips
                items={activeCategory.children}
                selected={selectedSubCategory}
                onSelect={setSelectedSubCategory}
              />
            </Box>
          )}
          <Box sx={{ mt: 2 }}>
            {loading ? (
              <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
            ) : products.length === 0 ? (
              <Typography color="text.secondary" textAlign="center" py={4}>
                Keine Produkte in dieser Kategorie
              </Typography>
            ) : (
              <ProductGrid
                items={products}
                cartQuantities={cartQuantities}
                orderQuantities={orderQuantities}
                inventoryQuantities={inventoryQuantities}
                subscribedIds={subscribedIds}
                onProductClick={onProductClick}
              />
            )}
          </Box>
        </Box>
      ) : (
        /* Search results */
        <Box sx={{ mt: 2 }}>
          {searchLoading ? (
            <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
          ) : products.length === 0 ? (
            <Typography color="text.secondary" textAlign="center" py={4}>
              Keine Ergebnisse
            </Typography>
          ) : (
            <ProductGrid
              items={products}
              cartQuantities={cartQuantities}
              orderQuantities={orderQuantities}
              inventoryQuantities={inventoryQuantities}
              subscribedIds={subscribedIds}
              onProductClick={onProductClick}
            />
          )}
        </Box>
      )}
    </Box>
  );
}
