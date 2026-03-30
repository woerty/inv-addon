import { useCallback, useEffect, useState } from "react";
import type { ChatMessage } from "../types";
import { sendChatMessage, clearChat, getChatHistory } from "../api/client";

export function useChat(sessionId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const data = await getChatHistory(sessionId);
      setMessages(data.messages);
    } catch {
      // No history yet
    }
  }, [sessionId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const send = async (message: string, useIngredients: boolean) => {
    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: message }]);

    try {
      const data = await sendChatMessage(message, sessionId, useIngredients);
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const clear = async () => {
    await clearChat(sessionId);
    setMessages([]);
  };

  return { messages, loading, error, send, clear };
}
