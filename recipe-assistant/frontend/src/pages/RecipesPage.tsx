import { useState } from "react";
import {
  Alert,
  Button,
  CircularProgress,
  Container,
  FormControlLabel,
  Paper,
  Switch,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getRecipeSuggestions, generateRecipeImage } from "../api/client";
import type { Recipe } from "../types";

const RecipesPage = () => {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recipeImage, setRecipeImage] = useState("");
  const [generateImages, setGenerateImages] = useState(false);

  const fetchRecipes = async () => {
    setLoading(true);
    setError("");
    setSelectedRecipe(null);

    try {
      const data = await getRecipeSuggestions();
      setRecipes(data.recipes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Abrufen der Rezepte.");
    } finally {
      setLoading(false);
    }
  };

  const handleRecipeClick = async (recipe: Recipe) => {
    setSelectedRecipe(recipe);
    setRecipeImage("");

    if (generateImages) {
      setLoading(true);
      try {
        const data = await generateRecipeImage(recipe.name);
        if (data.image_url) setRecipeImage(data.image_url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Fehler bei Bildgenerierung.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        KI-Kochassistent
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={generateImages}
            onChange={() => setGenerateImages(!generateImages)}
          />
        }
        label="Bilder für Rezepte generieren (DALL-E)"
        sx={{ mb: 2 }}
      />

      {recipes.length === 0 && (
        <Button
          variant="contained"
          onClick={fetchRecipes}
          disabled={loading}
          sx={{ mb: 2 }}
        >
          {loading ? <CircularProgress size={24} /> : "Rezeptvorschläge abrufen"}
        </Button>
      )}

      {error && (
        <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
          {error}
        </Alert>
      )}

      {!selectedRecipe && recipes.length > 0 && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {recipes.map((recipe, i) => (
            <Grid key={i} item xs={12} sm={6}>
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
          <Typography variant="subtitle1" color="text.secondary" gutterBottom>
            {selectedRecipe.short_description}
          </Typography>

          {recipeImage && (
            <img
              src={recipeImage}
              alt={selectedRecipe.name}
              style={{ width: "100%", borderRadius: 10, marginBottom: 10 }}
            />
          )}

          <Typography variant="h6">Zutaten:</Typography>
          <ul>
            {selectedRecipe.ingredients.map((ing, i) => (
              <li key={i}>{ing}</li>
            ))}
          </ul>

          <Typography variant="h6">Anleitung:</Typography>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {selectedRecipe.instructions}
          </ReactMarkdown>

          <Button
            variant="outlined"
            color="secondary"
            onClick={() => setSelectedRecipe(null)}
            sx={{ mt: 2 }}
          >
            Zurück zur Auswahl
          </Button>
        </Paper>
      )}
    </Container>
  );
};

export default RecipesPage;
