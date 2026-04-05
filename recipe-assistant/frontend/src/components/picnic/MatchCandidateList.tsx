import type { MatchSuggestion } from "../../types";

interface Props {
  suggestions: MatchSuggestion[];
  selectedBarcode: string | null;
  onSelect: (barcode: string | null) => void;
}

export function MatchCandidateList({ suggestions, selectedBarcode, onSelect }: Props) {
  if (suggestions.length === 0) {
    return <div className="text-sm text-gray-500">Kein Vorschlag</div>;
  }

  return (
    <ul className="space-y-1">
      {suggestions.map((s) => {
        const isSelected = s.inventory_barcode === selectedBarcode;
        const tier =
          s.score >= 92 ? "confident" : s.score >= 75 ? "uncertain" : "weak";
        return (
          <li key={s.inventory_barcode}>
            <button
              type="button"
              onClick={() => onSelect(isSelected ? null : s.inventory_barcode)}
              className={`w-full text-left px-2 py-1 rounded border ${
                isSelected
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
            >
              <div className="flex justify-between">
                <span>{s.inventory_name}</span>
                <span
                  className={`text-xs ${
                    tier === "confident"
                      ? "text-green-600"
                      : tier === "uncertain"
                      ? "text-yellow-600"
                      : "text-gray-500"
                  }`}
                >
                  {Math.round(s.score)} — {s.reason}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
