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
