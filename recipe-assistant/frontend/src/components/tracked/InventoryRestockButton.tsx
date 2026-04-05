import { Chip, IconButton, Tooltip } from "@mui/material";
import AddAlertIcon from "@mui/icons-material/AddAlert";
import type { TrackedProduct } from "../../types";

type Props = {
  tracked?: TrackedProduct;
  onClick: () => void;
};

const InventoryRestockButton = ({ tracked, onClick }: Props) => {
  if (!tracked) {
    return (
      <Tooltip title="Nachbestellungs-Regel anlegen">
        <IconButton size="small" onClick={onClick}>
          <AddAlertIcon fontSize="small" color="disabled" />
        </IconButton>
      </Tooltip>
    );
  }

  const label = `${tracked.current_quantity} / ${tracked.min_quantity}`;
  const color = tracked.below_threshold ? "error" : "success";

  return (
    <Tooltip
      title={`Nachbestellen bei < ${tracked.min_quantity}, auffüllen auf ${tracked.target_quantity}`}
    >
      <Chip
        label={label}
        color={color}
        size="small"
        onClick={onClick}
        clickable
      />
    </Tooltip>
  );
};

export default InventoryRestockButton;
