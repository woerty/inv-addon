import { useEffect, useState } from "react";
import {
  Button,
  IconButton,
  Paper,
  TextField,
  Typography,
  List,
  ListItem,
  ListItemText,
  Box,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import SaveIcon from "@mui/icons-material/Save";
import CancelIcon from "@mui/icons-material/Cancel";
import { useNotification } from "../components/NotificationProvider";
import { getPersons, createPerson, updatePerson, deletePerson } from "../api/client";
import type { Person } from "../types";

const PersonsPage = () => {
  const { notify } = useNotification();
  const [persons, setPersons] = useState<Person[]>([]);
  const [newName, setNewName] = useState("");
  const [newPrefs, setNewPrefs] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editPrefs, setEditPrefs] = useState("");

  const load = async () => {
    try {
      setPersons(await getPersons());
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Laden", "error");
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createPerson(newName.trim(), newPrefs.trim());
      setNewName("");
      setNewPrefs("");
      notify("Person angelegt", "success");
      await load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Person wirklich löschen?")) return;
    try {
      await deletePerson(id);
      notify("Person gelöscht", "success");
      await load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const startEdit = (person: Person) => {
    setEditingId(person.id);
    setEditName(person.name);
    setEditPrefs(person.preferences);
  };

  const handleSave = async () => {
    if (editingId === null) return;
    try {
      await updatePerson(editingId, { name: editName.trim(), preferences: editPrefs.trim() });
      setEditingId(null);
      notify("Gespeichert", "success");
      await load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Personen & Vorlieben
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Lege Personen an und trage ihre Essensvorlieben oder -einschränkungen ein.
        Bei den Rezeptvorschlägen kannst du auswählen, wer mitisst.
      </Typography>

      {/* Add new person */}
      <Box sx={{ mb: 3, p: 2, bgcolor: "#f5f5f5", borderRadius: 1 }}>
        <Typography variant="h6" gutterBottom>Neue Person</Typography>
        <TextField
          label="Name"
          fullWidth
          margin="normal"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <TextField
          label="Vorlieben / Einschränkungen (Freitext)"
          fullWidth
          multiline
          rows={3}
          margin="normal"
          placeholder="z.B. Vegetarisch, mag keinen Koriander, liebt Pasta, laktoseintolerant..."
          value={newPrefs}
          onChange={(e) => setNewPrefs(e.target.value)}
        />
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={!newName.trim()}
          sx={{ mt: 1 }}
        >
          Person anlegen
        </Button>
      </Box>

      {/* List of persons */}
      <List>
        {persons.map((person) => (
          <ListItem
            key={person.id}
            sx={{
              border: "1px solid #e0e0e0",
              borderRadius: 1,
              mb: 1,
              flexDirection: "column",
              alignItems: "stretch",
            }}
          >
            {editingId === person.id ? (
              <Box sx={{ width: "100%" }}>
                <TextField
                  label="Name"
                  fullWidth
                  margin="dense"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
                <TextField
                  label="Vorlieben / Einschränkungen"
                  fullWidth
                  multiline
                  rows={3}
                  margin="dense"
                  value={editPrefs}
                  onChange={(e) => setEditPrefs(e.target.value)}
                />
                <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
                  <IconButton color="primary" onClick={handleSave}><SaveIcon /></IconButton>
                  <IconButton onClick={() => setEditingId(null)}><CancelIcon /></IconButton>
                </Box>
              </Box>
            ) : (
              <Box sx={{ display: "flex", alignItems: "flex-start", width: "100%" }}>
                <ListItemText
                  primary={person.name}
                  secondary={person.preferences || "Keine Vorlieben eingetragen"}
                  secondaryTypographyProps={{ style: { whiteSpace: "pre-wrap" } }}
                />
                <IconButton onClick={() => startEdit(person)}><EditIcon /></IconButton>
                <IconButton color="error" onClick={() => handleDelete(person.id)}><DeleteIcon /></IconButton>
              </Box>
            )}
          </ListItem>
        ))}
        {persons.length === 0 && (
          <Typography color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
            Noch keine Personen angelegt.
          </Typography>
        )}
      </List>
    </Paper>
  );
};

export default PersonsPage;
