import { Paper, Typography } from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { StorageLocationCount } from "../../types";

interface Props {
  locations: StorageLocationCount[];
}

export default function StorageLocations({ locations }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Lagerorte
      </Typography>
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
