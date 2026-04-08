import Grid from "@mui/material/Grid";
import ProductCard from "./ProductCard";

interface ProductGridItem {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

interface ProductGridProps {
  items: ProductGridItem[];
  cartQuantities: Record<string, number>;
  orderQuantities: Record<string, number>;
  inventoryQuantities: Record<string, number>;
  subscribedIds: Set<string>;
  onProductClick: (picnicId: string) => void;
}

export default function ProductGrid({
  items, cartQuantities, orderQuantities, inventoryQuantities, subscribedIds, onProductClick,
}: ProductGridProps) {
  return (
    <Grid container spacing={2}>
      {items.map((item) => (
        <Grid item xs={6} sm={4} md={3} key={item.picnic_id}>
          <ProductCard
            picnicId={item.picnic_id}
            name={item.name}
            unitQuantity={item.unit_quantity}
            imageId={item.image_id}
            priceCents={item.price_cents}
            inCart={cartQuantities[item.picnic_id] ?? 0}
            onOrder={orderQuantities[item.picnic_id] ?? 0}
            inInventory={inventoryQuantities[item.picnic_id] ?? 0}
            isSubscribed={subscribedIds.has(item.picnic_id)}
            onClick={onProductClick}
          />
        </Grid>
      ))}
    </Grid>
  );
}
