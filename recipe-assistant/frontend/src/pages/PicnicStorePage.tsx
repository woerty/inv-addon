import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Container,
  Grid,
  TextField,
  Typography,
} from "@mui/material";
import { usePicnicSearch, usePicnicStatus } from "../hooks/usePicnic";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import { useNotification } from "../components/NotificationProvider";
import { addShoppingListItem } from "../api/client";
import StoreResultCard from "../components/picnic/StoreResultCard";
import SubscribeDialog from "../components/picnic/SubscribeDialog";
import type { PicnicSearchResult, TrackedProductCreate } from "../types";

const DEBOUNCE_MS = 400;

const PicnicStorePage = () => {
  const { status, loading: statusLoading } = usePicnicStatus();
  const { results, loading: searchLoading, search } = usePicnicSearch();
  const { items: tracked, create } = useTrackedProducts();
  const { notify } = useNotification();

  const [query, setQuery] = useState("");
  const [subscribeTarget, setSubscribeTarget] = useState<PicnicSearchResult | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const subscribedPicnicIds = useMemo(
    () => new Set(tracked.map((t) => t.picnic_id)),
    [tracked]
  );

  const handleQueryChange = useCallback(
    (value: string) => {
      setQuery(value);
      clearTimeout(timerRef.current);
      if (value.trim().length < 2) return;
      timerRef.current = setTimeout(() => search(value.trim()), DEBOUNCE_MS);
    },
    [search]
  );

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const handleAddToList = async (r: PicnicSearchResult) => {
    try {
      await addShoppingListItem({
        picnic_id: r.picnic_id,
        name: r.name,
        quantity: 1,
      });
      notify("Zur Einkaufsliste hinzugefügt", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const handleSubscribe = async (data: TrackedProductCreate) => {
    await create(data);
    notify("Abonniert", "success");
  };

  if (statusLoading) return null;
  if (!status?.enabled) {
    return (
      <Container sx={{ mt: 4 }}>
        <Alert severity="info">
          Picnic Store benötigt die Picnic-Integration. Bitte zuerst Picnic
          einrichten.
        </Alert>
      </Container>
    );
  }

  return (
    <Container sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        Picnic Store
      </Typography>
      <TextField
        fullWidth
        placeholder="Picnic durchsuchen..."
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        sx={{ mb: 3 }}
      />

      {searchLoading && (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      )}

      {!searchLoading && results.length === 0 && query.trim().length >= 2 && (
        <Typography color="text.secondary">Keine Ergebnisse.</Typography>
      )}

      <Grid container spacing={2}>
        {results.map((r) => (
          <Grid item xs={6} sm={4} md={3} key={r.picnic_id}>
            <StoreResultCard
              result={r}
              alreadySubscribed={subscribedPicnicIds.has(r.picnic_id)}
              onAddToList={handleAddToList}
              onSubscribe={setSubscribeTarget}
            />
          </Grid>
        ))}
      </Grid>

      <SubscribeDialog
        product={subscribeTarget}
        onClose={() => setSubscribeTarget(null)}
        onSubmit={handleSubscribe}
      />
    </Container>
  );
};

export default PicnicStorePage;
