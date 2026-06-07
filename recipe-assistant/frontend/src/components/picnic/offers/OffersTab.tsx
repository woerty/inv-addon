import { useMemo, useState } from "react";
import {
  Box, Card, CardActionArea, CardContent, CardMedia, Chip,
  CircularProgress, Grid, Stack, TextField, Typography,
} from "@mui/material";
import { usePicnicOffers } from "../../../hooks/usePicnicOffers";
import { useRegisterRefresh } from "../../RefreshProvider";
import { formatPrice } from "../../../utils/format";
import type { OfferItem } from "../../../types";

const imgUrl = (imageId: string | null, size = "medium") =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/${size}.png`
    : undefined;

function OfferCard({ offer, onClick }: { offer: OfferItem; onClick: (id: string) => void }) {
  const onSale = offer.original_price_cents != null && offer.price_cents != null;
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardActionArea onClick={() => onClick(offer.picnic_id)} sx={{ flex: 1, position: "relative" }}>
        {offer.promo_label && (
          <Chip
            label={offer.promo_label}
            size="small"
            color="error"
            sx={{ position: "absolute", top: 6, left: 6, zIndex: 1, fontWeight: 600 }}
          />
        )}
        <CardMedia
          component="img"
          height="140"
          image={imgUrl(offer.image_id)}
          alt={offer.name}
          sx={{ objectFit: "contain", p: 1, bgcolor: "#fafafa" }}
        />
        <CardContent sx={{ pb: 1 }}>
          <Typography variant="body2" fontWeight={500} noWrap>{offer.name}</Typography>
          <Stack direction="row" spacing={0.75} alignItems="baseline" sx={{ mt: 0.5 }}>
            {offer.price_cents != null && (
              <Typography variant="body2" fontWeight={700} color={onSale ? "error.main" : "text.primary"}>
                {formatPrice(offer.price_cents)}
              </Typography>
            )}
            {onSale && (
              <Typography variant="caption" color="text.secondary" sx={{ textDecoration: "line-through" }}>
                {formatPrice(offer.original_price_cents)}
              </Typography>
            )}
            {offer.unit_quantity && (
              <Typography variant="caption" color="text.secondary">· {offer.unit_quantity}</Typography>
            )}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

interface OffersTabProps {
  onProductClick: (picnicId: string) => void;
}

export default function OffersTab({ onProductClick }: OffersTabProps) {
  const { offers, loading, refetch } = usePicnicOffers();
  const [filter, setFilter] = useState("");
  useRegisterRefresh(refetch);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? offers.filter(o => o.name.toLowerCase().includes(q)) : offers;
  }, [offers, filter]);

  if (loading) return <Box display="flex" justifyContent="center" py={8}><CircularProgress /></Box>;

  if (offers.length === 0) {
    return <Typography color="text.secondary" sx={{ py: 4 }}>Aktuell keine Angebote.</Typography>;
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }} spacing={2}>
        <TextField
          size="small"
          placeholder="Angebote filtern…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          sx={{ flex: 1, maxWidth: 320 }}
        />
        <Typography variant="caption" color="text.secondary">{visible.length} Angebote</Typography>
      </Stack>
      <Grid container spacing={1.5}>
        {visible.map(offer => (
          <Grid key={offer.picnic_id} item xs={6} sm={4} md={3}>
            <OfferCard offer={offer} onClick={onProductClick} />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
