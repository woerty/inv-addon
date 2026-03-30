import { useCallback, useRef, useState } from "react";

interface UseScannerOptions {
  onScan: (barcode: string) => void;
  cooldownMs?: number;
}

export function useScanner({ onScan, cooldownMs = 2000 }: UseScannerOptions) {
  const [lastScanned, setLastScanned] = useState<string | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBarcodeRef = useRef<string | null>(null);

  const handleDecode = useCallback(
    (result: string) => {
      const barcode = result.trim();
      if (!barcode) return;

      if (barcode === lastBarcodeRef.current && cooldownRef.current) return;

      lastBarcodeRef.current = barcode;
      setLastScanned(barcode);
      onScan(barcode);

      if (cooldownRef.current) clearTimeout(cooldownRef.current);
      cooldownRef.current = setTimeout(() => {
        cooldownRef.current = null;
        lastBarcodeRef.current = null;
      }, cooldownMs);
    },
    [onScan, cooldownMs]
  );

  return { lastScanned, handleDecode };
}

export function useCameraSwitch() {
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");

  const toggle = useCallback(() => {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  }, []);

  return { facingMode, toggle };
}
