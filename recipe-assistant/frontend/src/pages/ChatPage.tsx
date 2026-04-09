import { useMemo, useState } from "react";
import {
  Box,
  Button,
  CircularProgress,
  Container,
  FormControlLabel,
  Paper,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat } from "../hooks/useChat";

const ChatPage = () => {
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const { messages, loading, error, send, clear } = useChat(sessionId);
  const [input, setInput] = useState("");
  const [useIngredients, setUseIngredients] = useState(false);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    send(input.trim(), useIngredients);
    setInput("");
  };

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        KI-Chat Assistent
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={useIngredients}
            onChange={() => setUseIngredients(!useIngredients)}
          />
        }
        label="Zutaten aus dem Inventar nutzen"
        sx={{ mb: 2 }}
      />

      <Paper
        variant="outlined"
        sx={{
          p: 2,
          maxHeight: "60vh",
          overflowY: "auto",
          mb: 2,
          display: "flex",
          flexDirection: "column",
          borderRadius: 3,
        }}
      >
        {messages.length === 0 ? (
          <Typography variant="body1" color="text.secondary">
            Starte eine Unterhaltung mit der KI!
          </Typography>
        ) : (
          messages.map((msg, i) => (
            <Paper
              key={i}
              sx={{
                p: 1,
                mb: 1,
                bgcolor: msg.role === "user" ? "rgba(21, 101, 192, 0.08)" : "rgba(46, 125, 50, 0.08)",
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "80%",
                borderRadius: 2,
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {msg.role === "user" ? "Du" : "Assistent"}
              </Typography>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
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
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        disabled={loading}
        sx={{ mb: 2 }}
      />

      <Box sx={{ display: "flex", gap: 2 }}>
        <Button
          variant="contained"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? <CircularProgress size={24} /> : "Senden"}
        </Button>
        <Button variant="outlined" color="secondary" onClick={clear}>
          Chat zurücksetzen
        </Button>
      </Box>
    </Container>
  );
};

export default ChatPage;
