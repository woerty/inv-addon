import type {
  InventoryItem,
  StorageLocation,
  Recipe,
  ChatMessage,
} from "../types";

const BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (e) {
    throw new Error(`Netzwerkfehler: Server nicht erreichbar (${path})`);
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = error?.detail || error?.message || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(detail);
  }
  return response.json();
}

// Inventory
export const getInventory = (search?: string, sortBy?: string, order?: string) => {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (sortBy) params.set("sort_by", sortBy);
  if (order) params.set("order", order);
  const qs = params.toString();
  return request<InventoryItem[]>(`/inventory/${qs ? `?${qs}` : ""}`);
};

export const addItemByBarcode = (barcode: string, storageLocation?: string, expirationDate?: string) =>
  request<{ message: string }>("/inventory/barcode", {
    method: "POST",
    body: JSON.stringify({
      barcode,
      storage_location: storageLocation || null,
      expiration_date: expirationDate || null,
    }),
  });

export const removeItemByBarcode = (barcode: string) =>
  request<{ message: string }>("/inventory/remove", {
    method: "POST",
    body: JSON.stringify({ barcode }),
  });

export const updateItem = (barcode: string, data: {
  quantity?: number;
  storage_location?: string;
  expiration_date?: string;
}) =>
  request<{ message: string }>(`/inventory/${barcode}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteItem = (barcode: string) =>
  request<{ message: string }>(`/inventory/${barcode}`, { method: "DELETE" });

// Storage Locations
export const getStorageLocations = () =>
  request<StorageLocation[]>("/storage-locations/");

export const createStorageLocation = (name: string) =>
  request<StorageLocation>("/storage-locations/", {
    method: "POST",
    body: JSON.stringify({ location_name: name }),
  });

export const deleteStorageLocation = (id: number) =>
  request<{ message: string }>(`/storage-locations/${id}`, { method: "DELETE" });

// Assistant
export const getRecipeSuggestions = () =>
  request<{ recipes: Recipe[] }>("/assistant/recipes");

export const generateRecipeImage = (name: string) =>
  request<{ image_url: string | null }>("/assistant/recipe-image", {
    method: "POST",
    body: JSON.stringify({ name, generate_image: true }),
  });

export const sendChatMessage = (message: string, sessionId: string, useIngredients: boolean) =>
  request<{ response: string; session_id: string }>("/assistant/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId, use_ingredients: useIngredients }),
  });

export const clearChat = (sessionId: string) =>
  request<{ message: string }>(`/assistant/chat/clear/${sessionId}`, { method: "POST" });

export const getChatHistory = (sessionId: string) =>
  request<{ messages: ChatMessage[]; session_id: string }>(
    `/assistant/chat/history/${sessionId}`
  );
