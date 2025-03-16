import React, { useState } from "react";
import { Container, TextField, Button, Paper, Typography, CircularProgress, Switch, FormControlLabel } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ChatAssistant = () => {
  const [messages, setMessages] = useState([]); // Speichert den Chatverlauf
  const [input, setInput] = useState(""); // Aktuelle Benutzereingabe
  const [loading, setLoading] = useState(false); // Ladeanzeige für KI-Antworten
  const [error, setError] = useState(""); // Fehlerbehandlung
  const [useIngredients, setUseIngredients] = useState(false); // Schalter für Zutaten-Zugriff

  // Nachricht an das Backend senden
  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = { role: "user", content: input };
    setMessages((prevMessages) => [...prevMessages, userMessage]); // Nachricht lokal anzeigen
    setInput(""); // Eingabefeld leeren
    setLoading(true);
    setError("");

    try {
      const response = await fetch("http://localhost:5000/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input, useIngredients }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Fehler beim Abrufen der Antwort.");
      }

      const assistantMessage = { role: "assistant", content: data.response };
      setMessages((prevMessages) => [...prevMessages, assistantMessage]); // Antwort von OpenAI anzeigen
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Chat zurücksetzen
  const clearChat = async () => {
    try {
      const response = await fetch("http://localhost:5000/assistant/clear-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        throw new Error("Fehler beim Zurücksetzen des Chats.");
      }

      setMessages([]); // Lokalen Chatverlauf löschen
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Container sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        KI-Chat Assistent
      </Typography>

      {/* Schalter für Zutaten-Zugriff */}
      <FormControlLabel
        control={<Switch checked={useIngredients} onChange={() => setUseIngredients(!useIngredients)} />}
        label="Zutaten aus dem Inventar nutzen"
        sx={{ mb: 2 }}
      />

      <Paper
        elevation={3}
        sx={{
          p: 2,
          maxHeight: "60vh",
          overflowY: "auto",
          mb: 2,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {messages.length === 0 ? (
          <Typography variant="body1" color="textSecondary">
            Starte eine Unterhaltung mit der KI!
          </Typography>
        ) : (
          messages.map((msg, index) => (
            <Paper
              key={index}
              sx={{
                p: 1,
                mb: 1,
                backgroundColor: msg.role === "user" ? "#e3f2fd" : "#f1f8e9",
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <Typography variant="caption" color="textSecondary">
                {msg.role === "user" ? "Du" : "Assistent"}
              </Typography>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </Paper>
          ))
        )}
      </Paper>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      <TextField
        fullWidth
        label="Nachricht eingeben..."
        variant="outlined"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && !loading && sendMessage()}
        disabled={loading}
        sx={{ mb: 2 }}
      />

      <Button variant="contained" color="primary" onClick={sendMessage} disabled={loading || !input.trim()} sx={{ mr: 2 }}>
        {loading ? <CircularProgress size={24} /> : "Senden"}
      </Button>

      <Button variant="outlined" color="secondary" onClick={clearChat}>
        Chat zurücksetzen
      </Button>
    </Container>
  );
};

export default ChatAssistant;
