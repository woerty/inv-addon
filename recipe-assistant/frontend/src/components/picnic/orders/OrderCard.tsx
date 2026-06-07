import { useState } from "react";
import {
  Box, Card, CardContent, Chip, Collapse, IconButton, Stack, Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { PendingOrder } from "../../../types";
import { formatPrice } from "../../../utils/format";
import { PICNIC_IMG_BG } from "../../../utils/picnic";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

const formatDate = (iso: string | null) => {
  if (!iso) return "Unbekannt";
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

interface OrderCardProps { order: PendingOrder; }

export default function OrderCard({ order }: OrderCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card variant="outlined" sx={{ mb: 1 }}>
      <CardContent sx={{ pb: expanded ? 1 : "16px !important" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="body1" fontWeight={500}>
              Lieferung {formatDate(order.delivery_time)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {order.total_items} Artikel
              {order.total_price_cents != null && ` · ${formatPrice(order.total_price_cents)}`}
            </Typography>
          </Box>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Chip label={order.status} size="small" variant="outlined" />
            <IconButton size="small" onClick={() => setExpanded(!expanded)}
              sx={{ transform: expanded ? "rotate(180deg)" : "none", transition: "0.2s" }}>
              <ExpandMoreIcon />
            </IconButton>
          </Stack>
        </Stack>
        <Collapse in={expanded}>
          <Stack spacing={1} sx={{ mt: 2 }}>
            {order.items.map((item, i) => {
              const onOffer = item.promo_price_cents != null && item.price_cents != null;
              return (
                <Stack key={i} direction="row" alignItems="center" spacing={1}>
                  {item.image_id && (
                    <Box component="img" src={imgUrl(item.image_id)} alt={item.name}
                      sx={{ width: 32, height: 32, objectFit: "contain", bgcolor: PICNIC_IMG_BG, borderRadius: 1, p: 0.5 }} />
                  )}
                  <Box flex={1} minWidth={0}>
                    <Typography variant="body2" noWrap>{item.name}</Typography>
                    {item.promo_text && (
                      <Chip label={item.promo_text} size="small" color="error" variant="outlined"
                        sx={{ height: 18, fontSize: "0.65rem", "& .MuiChip-label": { px: 0.75 } }} />
                    )}
                  </Box>
                  <Typography variant="body2" color="text.secondary">{item.quantity}x</Typography>
                  {item.price_cents != null && (
                    <Stack alignItems="flex-end" sx={{ minWidth: 64 }}>
                      {onOffer && (
                        <Typography variant="caption" color="text.secondary"
                          sx={{ textDecoration: "line-through", lineHeight: 1.1 }}>
                          {formatPrice(item.price_cents * item.quantity)}
                        </Typography>
                      )}
                      <Typography variant="body2" fontWeight={600}
                        color={onOffer ? "error.main" : "text.primary"}>
                        {formatPrice((onOffer ? item.promo_price_cents! : item.price_cents) * item.quantity)}
                      </Typography>
                    </Stack>
                  )}
                </Stack>
              );
            })}
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}
