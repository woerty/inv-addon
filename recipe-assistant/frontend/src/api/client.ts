import type {
  InventoryItem,
  StorageLocation,
  Recipe,
  ChatMessage,
  Person,
  PicnicStatus,
  PicnicLoginStartStatus,
  PicnicLoginChannel,
  ImportFetchResponse,
  ImportDecision,
  ImportCommitResponse,
  ShoppingListItem as PicnicShoppingListItem,
  PicnicSearchResult,
  CartSyncResponse,
} from "../types";

const BASE = "./api";

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
    const rawDetail = error?.detail ?? error?.message;
    let detail: string;
    if (typeof rawDetail === "string") {
      detail = rawDetail;
    } else if (rawDetail && typeof rawDetail === "object") {
      // FastAPI HTTPException(detail={...}) returns a structured object.
      // Prefer a known "error" token, otherwise fall back to JSON.
      detail = rawDetail.error || rawDetail.message || JSON.stringify(rawDetail);
    } else {
      detail = `HTTP ${response.status}: ${response.statusText}`;
    }
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

export const relookupBarcode = (barcode: string) =>
  request<{ message: string; updated: boolean }>(`/inventory/relookup/${barcode}`, { method: "POST" });

export const relookupAllUnknown = () =>
  request<{ message: string; updated: number }>("/inventory/relookup-all", { method: "POST" });

export const exportData = async (): Promise<Blob> => {
  const response = await fetch(`${BASE}/inventory/export`);
  if (!response.ok) throw new Error("Export fehlgeschlagen");
  return response.blob();
};

export const importData = async (file: File): Promise<{ message: string }> => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${BASE}/inventory/import`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || "Import fehlgeschlagen");
  }
  return response.json();
};

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

// Persons
export const getPersons = () =>
  request<Person[]>("/persons/");

export const createPerson = (name: string, preferences: string = "") =>
  request<Person>("/persons/", {
    method: "POST",
    body: JSON.stringify({ name, preferences }),
  });

export const updatePerson = (id: number, data: { name?: string; preferences?: string }) =>
  request<Person>(`/persons/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deletePerson = (id: number) =>
  request<{ message: string }>(`/persons/${id}`, { method: "DELETE" });

// Assistant
export const getRecipeSuggestions = (personIds?: number[]) => {
  const params = personIds?.length ? `?person_ids=${personIds.join(",")}` : "";
  return request<{ recipes: Recipe[] }>(`/assistant/recipes${params}`);
};

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

// Picnic
export const getPicnicStatus = () =>
  request<PicnicStatus>("/picnic/status");

export const fetchPicnicImport = () =>
  request<ImportFetchResponse>("/picnic/import/fetch", { method: "POST" });

export const commitPicnicImport = (delivery_id: string, decisions: ImportDecision[]) =>
  request<ImportCommitResponse>("/picnic/import/commit", {
    method: "POST",
    body: JSON.stringify({ delivery_id, decisions }),
  });

export const searchPicnic = (q: string) =>
  request<{ results: PicnicSearchResult[] }>(`/picnic/search?q=${encodeURIComponent(q)}`);

export const getShoppingList = () =>
  request<PicnicShoppingListItem[]>("/picnic/shopping-list");

export const addShoppingListItem = (data: {
  inventory_barcode?: string;
  picnic_id?: string;
  name: string;
  quantity: number;
}) =>
  request<PicnicShoppingListItem>("/picnic/shopping-list", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateShoppingListItem = (id: number, data: { quantity?: number; picnic_id?: string }) =>
  request<PicnicShoppingListItem>(`/picnic/shopping-list/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteShoppingListItem = (id: number) =>
  request<{ message: string }>(`/picnic/shopping-list/${id}`, { method: "DELETE" });

export const syncShoppingListToCart = () =>
  request<CartSyncResponse>("/picnic/shopping-list/sync", { method: "POST" });

export const startPicnicLogin = () =>
  request<{ status: PicnicLoginStartStatus }>("/picnic/login/start", { method: "POST" });

export const sendPicnicLoginCode = (channel: PicnicLoginChannel) =>
  request<{ status: "sent" }>("/picnic/login/send-code", {
    method: "POST",
    body: JSON.stringify({ channel }),
  });

export const verifyPicnicLoginCode = (code: string) =>
  request<{ status: "ok" }>("/picnic/login/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
