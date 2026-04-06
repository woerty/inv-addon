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
  image_id: string | null;
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

export interface ShoppingListItem {
  id: number;
  inventory_barcode: string | null;
  picnic_id: string | null;
  picnic_name: string | null;
  name: string;
  quantity: number;
  picnic_status: "mapped" | "unavailable";
  added_at: string;
}

export interface PicnicSearchResult {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

export interface CartSyncItemResult {
  shopping_list_id: number;
  picnic_id: string | null;
  status: "added" | "skipped_unmapped" | "failed";
  failure_reason: string | null;
}

export interface CartSyncResponse {
  results: CartSyncItemResult[];
  added_count: number;
  failed_count: number;
  skipped_count: number;
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
