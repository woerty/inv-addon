import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Typography,
} from "@mui/material";
import type { PicnicSearchResult } from "../../types";

const PICNIC_IMAGE_BASE =
  "https://storefront-prod.de.picnicinternational.com/static/images";

type Props = {
  result: PicnicSearchResult;
  alreadySubscribed: boolean;
  onAddToList: (result: PicnicSearchResult) => void;
  onSubscribe: (result: PicnicSearchResult) => void;
};

const StoreResultCard = ({
  result,
  alreadySubscribed,
  onAddToList,
  onSubscribe,
}: Props) => {
  const priceFormatted =
    result.price_cents != null
      ? (result.price_cents / 100).toFixed(2).replace(".", ",") + " €"
      : null;

  return (
    <Card sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {result.image_id && (
        <Box
          component="img"
          src={`${PICNIC_IMAGE_BASE}/${result.image_id}/medium.png`}
          alt=""
          sx={{ width: "100%", height: 140, objectFit: "contain", mt: 1 }}
        />
      )}
      <CardContent sx={{ flex: 1 }}>
        <Typography variant="subtitle2" gutterBottom>
          {result.name}
        </Typography>
        {result.unit_quantity && (
          <Typography variant="body2" color="text.secondary">
            {result.unit_quantity}
          </Typography>
        )}
        {priceFormatted && (
          <Typography variant="body2" fontWeight="bold" sx={{ mt: 0.5 }}>
            {priceFormatted}
          </Typography>
        )}
      </CardContent>
      <CardActions sx={{ flexDirection: "column", alignItems: "stretch", gap: 0.5, p: 1 }}>
        <Button size="small" onClick={() => onAddToList(result)}>
          In Einkaufsliste
        </Button>
        {alreadySubscribed ? (
          <Chip label="Abonniert" size="small" color="success" />
        ) : (
          <Button size="small" variant="outlined" onClick={() => onSubscribe(result)}>
            Abonnieren
          </Button>
        )}
      </CardActions>
    </Card>
  );
};

export default StoreResultCard;
