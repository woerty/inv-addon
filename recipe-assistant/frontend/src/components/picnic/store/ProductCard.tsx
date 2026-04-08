import {
  Card, CardActionArea, CardContent, CardMedia, Chip, Stack, Typography,
} from "@mui/material";
import RepeatIcon from "@mui/icons-material/Repeat";

interface ProductCardProps {
  picnicId: string;
  name: string;
  unitQuantity: string | null;
  imageId: string | null;
  priceCents: number | null;
  inCart: number;
  onOrder: number;
  inInventory: number;
  isSubscribed: boolean;
  onClick: (picnicId: string) => void;
}

const imgUrl = (imageId: string | null, size = "medium") =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/${size}.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

export default function ProductCard({
  picnicId, name, unitQuantity, imageId, priceCents,
  inCart, onOrder, inInventory, isSubscribed, onClick,
}: ProductCardProps) {
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardActionArea onClick={() => onClick(picnicId)} sx={{ flex: 1 }}>
        <CardMedia
          component="img"
          height="140"
          image={imgUrl(imageId)}
          alt={name}
          sx={{ objectFit: "contain", p: 1, bgcolor: "#fafafa" }}
        />
        <CardContent sx={{ pb: 1 }}>
          <Typography variant="body2" fontWeight={500} noWrap>{name}</Typography>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
            {unitQuantity && (
              <Typography variant="caption" color="text.secondary">{unitQuantity}</Typography>
            )}
            {priceCents != null && (
              <Typography variant="caption" fontWeight={600}>{formatPrice(priceCents)}</Typography>
            )}
            {isSubscribed && <RepeatIcon sx={{ fontSize: 14, color: "text.secondary" }} />}
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
            {inCart > 0 && <Chip label={`${inCart} im Warenkorb`} size="small" color="primary" />}
            {onOrder > 0 && <Chip label={`${onOrder} in Bestellung`} size="small" color="warning" />}
            {inInventory > 0 && <Chip label={`${inInventory} im Inventar`} size="small" color="success" />}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
