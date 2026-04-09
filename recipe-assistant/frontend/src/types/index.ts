export interface StorageLocation {
  id: number;
  name: string;
}

export interface InventoryItem {
  id: number;
  barcode: string;
  name: string;
  quantity: number;
  category: string;
  storage_location: StorageLocation | null;
  expiration_date: string | null;
  image_url: string | null;
  added_date: string;
  updated_date: string;
}

export interface Recipe {
  name: string;
  short_description: string;
  ingredients: string[];
  instructions: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface Person {
  id: number;
  name: string;
  preferences: string;
}

// --- Picnic ---

export interface PicnicStatus {
  enabled: boolean;
  needs_login: boolean;
  account: { first_name: string; last_name: string; email: string } | null;
}

export type PicnicLoginChannel = "SMS" | "EMAIL";

export type PicnicLoginStartStatus = "ok" | "awaiting_2fa";

export interface MatchSuggestion {
  inventory_barcode: string;
  inventory_name: string;
  score: number;
  reason: string;
}

export interface ImportCandidate {
  picnic_id: string;
  picnic_name: string;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  ordered_quantity: number;
  match_suggestions: MatchSuggestion[];
  best_confidence: number;
}

export interface ImportDelivery {
  delivery_id: string;
  delivered_at: string | null;
  items: ImportCandidate[];
}

export interface ImportFetchResponse {
  deliveries: ImportDelivery[];
}

export type ImportAction = "match_existing" | "create_new" | "skip";

export interface ImportDecision {
  picnic_id: string;
  action: ImportAction;
  target_barcode?: string | null;
  scanned_ean?: string | null;
  storage_location?: string | null;
  expiration_date?: string | null;
}

export interface ImportCommitResponse {
  imported: number;
  created: number;
  skipped: number;
  promoted: number;
}

export interface PicnicSearchResult {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

// ── Cart (Picnic as source of truth) ──────────────────────────────

export interface CartItem {
  picnic_id: string;
  name: string;
  quantity: number;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
  total_price_cents: number | null;
}

export interface Cart {
  items: CartItem[];
  total_items: number;
  total_price_cents: number;
}

// ── Pending Orders ────────────────────────────────────────────────

export interface PendingOrderItem {
  picnic_id: string;
  name: string;
  quantity: number;
  image_id: string | null;
  price_cents: number | null;
}

export interface PendingOrder {
  delivery_id: string;
  status: string;
  delivery_time: string | null;
  total_items: number;
  items: PendingOrderItem[];
}

export interface PendingOrdersResponse {
  orders: PendingOrder[];
  quantity_map: Record<string, number>;
}

// ── Product Detail ────────────────────────────────────────────────

export interface ProductDetail {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
  description: string | null;
  in_cart: number;
  on_order: number;
  inventory_quantity: number;
  is_subscribed: boolean;
}

// ── Categories ────────────────────────────────────────────────────

export interface CategoryItem {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

export interface SubCategory {
  id: string;
  name: string;
  image_id: string | null;
  items: CategoryItem[];
}

export interface PicnicCategory {
  id: string;
  name: string;
  image_id: string | null;
  children: SubCategory[];
}

// Tracked products (auto-restock)
export interface TrackedProduct {
  barcode: string;
  picnic_id: string;
  name: string;
  picnic_name: string;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  min_quantity: number;
  target_quantity: number;
  current_quantity: number;
  below_threshold: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrackedProductCreate {
  barcode?: string | null;
  picnic_id?: string;
  name?: string;
  min_quantity: number;
  target_quantity: number;
}

export interface TrackedProductUpdate {
  min_quantity?: number;
  target_quantity?: number;
}

export interface ResolvePreview {
  resolved: boolean;
  picnic_id: string | null;
  picnic_name: string | null;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  reason: string | null;
}

export interface PromoteBarcodeResponse {
  tracked: TrackedProduct;
  merged: boolean;
}

// ── Dashboard ────────────────────────────────────────────────────

export interface PinnedProduct {
  barcode: string;
  name: string;
  quantity: number;
  min_quantity: number | null;
  image_url: string | null;
}

export interface LowStockItem {
  barcode: string;
  name: string;
  quantity: number;
  min_quantity: number;
}

export interface ActivityEntry {
  action: string;
  barcode: string;
  product_name: string;
  details: string | null;
  timestamp: string;
}

export interface TrendSeries {
  category: string;
  data: number[];
}

export interface ConsumptionTrend {
  labels: string[];
  series: TrendSeries[];
}

export interface TopConsumer {
  barcode: string;
  name: string;
  count: number;
  sparkline: number[];
}

export interface CategoryCount {
  category: string;
  inventory_count: number;
  on_order_count: number;
}

export interface WeeklyCost {
  week: string;
  cents: number;
}

export interface RestockCosts {
  total_cents: number;
  previous_period_cents: number;
  weekly: WeeklyCost[];
}

export interface StorageLocationCount {
  name: string;
  item_count: number;
}

export interface DashboardSummary {
  pinned_products: PinnedProduct[];
  low_stock: LowStockItem[];
  recent_activity: ActivityEntry[];
  consumption_trend: ConsumptionTrend;
  top_consumers: TopConsumer[];
  categories: CategoryCount[];
  restock_costs: RestockCosts;
  storage_locations: StorageLocationCount[];
}

export interface ProductHistoryEntry {
  timestamp: string;
  quantity_after: number;
  action: string;
}

export interface ProductStats {
  total_consumed: number;
  avg_per_week: number;
  times_restocked: number;
  total_cost_cents: number;
  estimated_days_remaining: number | null;
}

export interface DashboardProductDetail {
  barcode: string;
  name: string;
  current_quantity: number;
  min_quantity: number | null;
  history: ProductHistoryEntry[];
  stats: ProductStats;
}
