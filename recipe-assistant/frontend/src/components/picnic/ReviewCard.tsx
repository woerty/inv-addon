import { useState } from "react";
import type { ImportCandidate, ImportDecision } from "../../types";
import { MatchCandidateList } from "./MatchCandidateList";

interface Props {
  candidate: ImportCandidate;
  storageLocations: string[];
  onChange: (decision: ImportDecision) => void;
}

export function ReviewCard({ candidate, storageLocations, onChange }: Props) {
  const confident = candidate.best_confidence >= 92;
  const initialAction = confident ? "match_existing" : "skip";
  const initialTarget = confident ? (candidate.match_suggestions[0]?.inventory_barcode ?? null) : null;

  const [action, setAction] = useState<ImportDecision["action"]>(initialAction);
  const [targetBarcode, setTargetBarcode] = useState<string | null>(initialTarget);
  const [storageLocation, setStorageLocation] = useState<string>(storageLocations[0] ?? "");

  const update = (patch: Partial<ImportDecision>) => {
    const next: ImportDecision = {
      picnic_id: candidate.picnic_id,
      action,
      target_barcode: targetBarcode,
      storage_location: action === "create_new" ? storageLocation : null,
      ...patch,
    };
    onChange(next);
  };

  return (
    <div className="border rounded p-4 space-y-3">
      <div className="flex gap-3">
        {candidate.picnic_image_id && (
          <img
            src={`https://storefront-prod.de.picnicinternational.com/static/images/${candidate.picnic_image_id}/tile-small.png`}
            alt=""
            className="w-16 h-16 object-contain"
          />
        )}
        <div className="flex-1">
          <div className="font-semibold">{candidate.picnic_name}</div>
          <div className="text-sm text-gray-600">
            {candidate.picnic_unit_quantity} × {candidate.ordered_quantity}
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => { setAction("match_existing"); update({ action: "match_existing" }); }}
          className={`px-3 py-1 rounded ${action === "match_existing" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Zuordnen
        </button>
        <button
          type="button"
          onClick={() => { setAction("create_new"); update({ action: "create_new" }); }}
          className={`px-3 py-1 rounded ${action === "create_new" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Neu anlegen
        </button>
        <button
          type="button"
          onClick={() => { setAction("skip"); update({ action: "skip" }); }}
          className={`px-3 py-1 rounded ${action === "skip" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Überspringen
        </button>
      </div>

      {action === "match_existing" && (
        <MatchCandidateList
          suggestions={candidate.match_suggestions}
          selectedBarcode={targetBarcode}
          onSelect={(b) => { setTargetBarcode(b); update({ target_barcode: b }); }}
        />
      )}

      {action === "create_new" && (
        <div>
          <label className="block text-sm font-medium">Lagerort</label>
          <select
            value={storageLocation}
            onChange={(e) => { setStorageLocation(e.target.value); update({ storage_location: e.target.value }); }}
            className="border rounded px-2 py-1"
          >
            {storageLocations.map((loc) => (
              <option key={loc} value={loc}>{loc}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
