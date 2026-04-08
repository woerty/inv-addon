import { useCallback, useMemo, useState } from "react";
import { Alert, Badge, Box, CircularProgress, Container, Tab, Tabs } from "@mui/material";
import { usePicnicStatus } from "../hooks/usePicnic";
import { usePicnicCart } from "../hooks/usePicnicCart";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import StoreTab from "../components/picnic/store/StoreTab";
import CartTab from "../components/picnic/cart/CartTab";
import OrdersTab from "../components/picnic/orders/OrdersTab";
import SubscriptionsTab from "../components/picnic/subscriptions/SubscriptionsTab";
import ProductDetailModal from "../components/picnic/store/ProductDetailModal";
import SubscribeDialog from "../components/picnic/SubscribeDialog";
import type { PicnicSearchResult, TrackedProductCreate } from "../types";

export default function PicnicStorePage() {
  const { status, loading: statusLoading } = usePicnicStatus();
  const { cart, loading: cartLoading, add: cartAdd, remove: cartRemove, clear: cartClear } = usePicnicCart();
  const { orders, quantityMap: orderQuantities, loading: ordersLoading } = usePicnicPendingOrders();
  const { items: tracked, create: createTracked } = useTrackedProducts();

  const [tab, setTab] = useState(0);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [subscribeTarget, setSubscribeTarget] = useState<PicnicSearchResult | null>(null);

  const cartQuantities = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of cart?.items ?? []) map[item.picnic_id] = item.quantity;
    return map;
  }, [cart]);

  const inventoryQuantities = useMemo<Record<string, number>>(() => ({}), []);

  const subscribedIds = useMemo(() => new Set(tracked.map(t => t.picnic_id)), [tracked]);

  const handleCartAdd = useCallback(async (picnicId: string, count = 1) => {
    await cartAdd(picnicId, count);
  }, [cartAdd]);

  const handleCartRemove = useCallback(async (picnicId: string, count = 1) => {
    await cartRemove(picnicId, count);
  }, [cartRemove]);

  const handleCartClear = useCallback(async () => {
    await cartClear();
  }, [cartClear]);

  const handleSubscribe = useCallback(async (data: TrackedProductCreate) => {
    await createTracked(data);
    setSubscribeTarget(null);
  }, [createTracked]);

  if (statusLoading) return <Box display="flex" justifyContent="center" py={8}><CircularProgress /></Box>;
  if (!status?.enabled) return <Container maxWidth="sm" sx={{ mt: 4 }}><Alert severity="info">Picnic ist nicht konfiguriert.</Alert></Container>;

  return (
    <Container maxWidth="lg" sx={{ mt: 2, mb: 4 }}>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Store" />
        <Tab label={<Badge badgeContent={cart?.total_items ?? 0} color="primary" max={99}><Box sx={{ px: 1 }}>Warenkorb</Box></Badge>} />
        <Tab label="Bestellungen" />
        <Tab label="Abos" />
      </Tabs>

      {tab === 0 && <StoreTab cartQuantities={cartQuantities} orderQuantities={orderQuantities} inventoryQuantities={inventoryQuantities} subscribedIds={subscribedIds} onProductClick={setDetailId} />}
      {tab === 1 && <CartTab cart={cart} loading={cartLoading} onAdd={handleCartAdd} onRemove={handleCartRemove} onClear={handleCartClear} onProductClick={setDetailId} />}
      {tab === 2 && <OrdersTab orders={orders} loading={ordersLoading} />}
      {tab === 3 && <SubscriptionsTab orderQuantities={orderQuantities} />}

      <ProductDetailModal
        picnicId={detailId}
        onClose={() => setDetailId(null)}
        onCartAdd={handleCartAdd}
        onCartRemove={handleCartRemove}
        onSubscribe={(picnicId, name) =>
          setSubscribeTarget({ picnic_id: picnicId, name, image_id: null, unit_quantity: null, price_cents: null })
        }
      />

      <SubscribeDialog
        product={subscribeTarget}
        onClose={() => setSubscribeTarget(null)}
        onSubmit={handleSubscribe}
      />
    </Container>
  );
}
