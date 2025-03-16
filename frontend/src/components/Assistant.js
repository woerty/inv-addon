import React, { useState } from "react";
import { Container, Typography, Button, CircularProgress, Alert, Paper, Grid, Switch, FormControlLabel } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const RecipeAssistant = () => {
  const [recipes, setRecipes] = useState([]);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recipeImage, setRecipeImage] = useState("");
  const [generateImages, setGenerateImages] = useState(false); // Bilder generieren?

const fetchRecipes = async () => {
    setLoading(true);
    setError("");
    setSelectedRecipe(null);

    try {
      const response = await fetch("http://localhost:5000/assistant/recipe-suggestions");
      const data = await response.json();
      
      console.log("API Response:", data); // Debugging

      if (!response.ok || !data.recipes) {
        throw new Error(data.error || "Fehler beim Abrufen der Rezepte.");
      }

      let parsedRecipes;
      try {
        parsedRecipes = JSON.parse(data.recipes).recipes; // ❗ API-String korrekt in JSON umwandeln
      } catch (e) {
        throw new Error("Die KI hat die Antwort nicht im richtigen JSON-Format zurückgegeben.");
      }

      setRecipes(parsedRecipes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
};



  const fetchRecipeImage = async (recipeName) => {
    if (!generateImages) return; // Bildgenerierung ist deaktiviert

    setLoading(true);
    setError("");

    try {
      const response = await fetch("http://localhost:5000/assistant/recipe-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: recipeName, generate_image: generateImages }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Fehler beim Generieren des Rezeptbilds.");
      }

      setRecipeImage(data.image_url);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRecipeClick = async (recipe) => {
    setSelectedRecipe(recipe);
    setRecipeImage(""); // Bild zurücksetzen
    await fetchRecipeImage(recipe.name);
  };

  return (
    <Container>
      <Typography variant="h4" gutterBottom>
        KI-Kochassistent
      </Typography>

      <FormControlLabel
        control={<Switch checked={generateImages} onChange={() => setGenerateImages(!generateImages)} />}
        label="Bilder für Rezepte generieren"
        sx={{ mb: 2 }}
      />

      {!recipes.length && (
        <Button variant="contained" color="primary" onClick={fetchRecipes} disabled={loading} sx={{ mb: 2 }}>
          {loading ? <CircularProgress size={24} /> : "Rezeptvorschläge abrufen"}
        </Button>
      )}

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

      {!selectedRecipe && recipes.length > 0 && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {recipes.map((recipe, index) => (
            <Grid item xs={12} sm={6} key={index}>
              <Button
                variant="contained"
                fullWidth
                onClick={() => handleRecipeClick(recipe)}
              >
                {recipe.name}
              </Button>
            </Grid>
          ))}
        </Grid>
      )}

      {selectedRecipe && (
        <Paper elevation={3} sx={{ mt: 2, p: 2, maxHeight: "60vh", overflowY: "auto" }}>
          <Typography variant="h5" gutterBottom>
            {selectedRecipe.name}
          </Typography>
          <Typography variant="subtitle1" color="textSecondary" gutterBottom>
            {selectedRecipe.short_description}
          </Typography>
          
          {recipeImage && (
            <img src={recipeImage} alt={selectedRecipe.name} style={{ width: "100%", borderRadius: "10px", marginBottom: "10px" }} />
          )}

          <Typography variant="h6">Zutaten:</Typography>
          <ul>
            {selectedRecipe.ingredients.map((ingredient, index) => (
              <li key={index}>{ingredient}</li>
            ))}
          </ul>
          <Typography variant="h6">Anleitung:</Typography>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {Array.isArray(selectedRecipe.instructions)
              ? selectedRecipe.instructions.join("\n\n") // Array in String umwandeln mit Zeilenumbrüchen
              : selectedRecipe.instructions}
          </ReactMarkdown>          <Button variant="outlined" color="secondary" onClick={() => setSelectedRecipe(null)} sx={{ mt: 2 }}>
          Zurück zur Auswahl
          </Button>
        </Paper>
      )}
    </Container>
  );
};

export default RecipeAssistant;
