import { Box, Paper, Typography } from "@mui/material";
import WarehouseIcon from "@mui/icons-material/Warehouse";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { StorageLocationCount } from "../../types";

interface Props {
  locations: StorageLocationCount[];
}

export default function StorageLocations({ locations }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <WarehouseIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Lagerorte</Typography>
      </Box>
      {locations.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Lagerorte</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={locations} layout="vertical">
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
            <Tooltip />
            <Bar dataKey="item_count" name="Artikel" fill="#26a69a" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
