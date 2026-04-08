import { Chip, Stack } from "@mui/material";

interface CategoryChipsProps {
  items: { id: string; name: string }[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export default function CategoryChips({ items, selected, onSelect }: CategoryChipsProps) {
  return (
    <Stack direction="row" spacing={1} sx={{ overflowX: "auto", pb: 1 }}>
      {items.map((cat) => (
        <Chip
          key={cat.id}
          label={cat.name}
          variant={selected === cat.id ? "filled" : "outlined"}
          color={selected === cat.id ? "primary" : "default"}
          onClick={() => onSelect(selected === cat.id ? null : cat.id)}
        />
      ))}
    </Stack>
  );
}
