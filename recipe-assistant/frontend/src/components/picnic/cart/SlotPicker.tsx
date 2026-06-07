import { Box, CircularProgress, FormControlLabel, Radio, RadioGroup, Typography } from "@mui/material";
import type { DeliverySlot } from "../../../types";

function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

interface SlotPickerProps {
  slots: DeliverySlot[];
  selectedSlotId: string | null;
  loading: boolean;
  disabled?: boolean;
  onSelect: (slotId: string) => void;
}

export default function SlotPicker({ slots, selectedSlotId, loading, disabled, onSelect }: SlotPickerProps) {
  if (loading) {
    return <Box display="flex" justifyContent="center" py={2}><CircularProgress size={24} /></Box>;
  }
  if (slots.length === 0) {
    return <Typography color="text.secondary" variant="body2">Keine Lieferzeiten verfügbar.</Typography>;
  }

  // Group consecutive slots by day; the list arrives already sorted by start time.
  const groups: { day: string; slots: DeliverySlot[] }[] = [];
  for (const slot of slots) {
    const day = fmtDay(slot.window_start);
    let group = groups.find(g => g.day === day);
    if (!group) {
      group = { day, slots: [] };
      groups.push(group);
    }
    group.slots.push(slot);
  }

  return (
    <RadioGroup value={selectedSlotId ?? ""} onChange={e => onSelect(e.target.value)}>
      {groups.map(group => (
        <Box key={group.day} sx={{ mb: 0.5 }}>
          <Typography variant="subtitle2" sx={{ mt: 1 }}>{group.day}</Typography>
          {group.slots.map(slot => (
            <FormControlLabel
              key={slot.slot_id}
              value={slot.slot_id}
              control={<Radio size="small" />}
              disabled={disabled || !slot.is_available}
              label={`${fmtTime(slot.window_start)} – ${fmtTime(slot.window_end)}`}
            />
          ))}
        </Box>
      ))}
    </RadioGroup>
  );
}
