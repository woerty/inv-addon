import { Box, Paper, Typography } from "@mui/material";
import CategoryIcon from "@mui/icons-material/Category";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { CategoryCount } from "../../types";

interface Props {
  categories: CategoryCount[];
}

export default function CategoryBreakdown({ categories }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <CategoryIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Kategorien</Typography>
      </Box>
      {categories.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Daten</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={categories} layout="vertical">
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={100} />
            <Tooltip />
            <Legend />
            <Bar dataKey="inventory_count" name="Bestand" fill="#5c6bc0" stackId="a" />
            <Bar dataKey="on_order_count" name="Bestellt" fill="#26a69a" stackId="a" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
