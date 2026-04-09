import { useEffect, useState } from "react";
import { Box, ToggleButton, ToggleButtonGroup, Typography, CircularProgress } from "@mui/material";
import { useDashboard, useProductDetail } from "../hooks/useDashboard";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { usePicnicStatus } from "../hooks/usePicnic";
import { getCart } from "../api/client";
import PinnedProducts from "../components/dashboard/PinnedProducts";
import PendingOrders from "../components/dashboard/PendingOrders";
import LowStockAlerts from "../components/dashboard/LowStockAlerts";
import RecentActivity from "../components/dashboard/RecentActivity";
import ConsumptionTrend from "../components/dashboard/ConsumptionTrend";
import TopConsumers from "../components/dashboard/TopConsumers";
import CategoryBreakdown from "../components/dashboard/CategoryBreakdown";
import RestockCostsWidget from "../components/dashboard/RestockCostsWidget";
import StorageLocations from "../components/dashboard/StorageLocations";
import ProductDetail from "../components/dashboard/ProductDetail";
import type { Cart } from "../types";

const DashboardPage = () => {
  const [days, setDays] = useState(30);
  const { data, loading } = useDashboard(days);
  const productDetail = useProductDetail();
  const { status: picnicStatus } = usePicnicStatus();
  const { orders } = usePicnicPendingOrders();

  // Fetch cart only if Picnic is enabled
  const [cart, setCart] = useState<Cart | null>(null);
  useEffect(() => {
    if (picnicStatus?.enabled) {
      getCart().then(setCart).catch(() => {});
    }
  }, [picnicStatus?.enabled]);

  const handleProductSelect = (barcode: string) => {
    productDetail.fetch(barcode, days);
  };

  if (loading && !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) return null;

  return (
    <Box sx={{ p: 2, maxWidth: 1200, mx: "auto" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="h5">Dashboard</Typography>
        <ToggleButtonGroup
          value={days}
          exclusive
          onChange={(_, v) => v !== null && setDays(v)}
          size="small"
        >
          <ToggleButton value={7}>7T</ToggleButton>
          <ToggleButton value={30}>30T</ToggleButton>
          <ToggleButton value={90}>90T</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Live Status */}
      <Typography variant="overline" color="text.secondary">Live Status</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2, mb: 3 }}>
        <PinnedProducts products={data.pinned_products} />
        {picnicStatus?.enabled && (
          <PendingOrders orders={orders ?? []} cart={cart} />
        )}
        <LowStockAlerts items={data.low_stock} />
        <RecentActivity entries={data.recent_activity} />
      </Box>

      {/* Analyse */}
      <Typography variant="overline" color="text.secondary">Analyse</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        <Box sx={{ gridColumn: { md: "1 / -1" } }}>
          <ConsumptionTrend trend={data.consumption_trend} />
        </Box>
        <TopConsumers consumers={data.top_consumers} onSelect={handleProductSelect} />
        <CategoryBreakdown categories={data.categories} />
        <RestockCostsWidget costs={data.restock_costs} />
        <StorageLocations locations={data.storage_locations} />
        {productDetail.data && (
          <ProductDetail detail={productDetail.data} onClose={productDetail.close} />
        )}
      </Box>
    </Box>
  );
};

export default DashboardPage;
