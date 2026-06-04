# Dark mode: restyle the add-on to Home Assistant's default dark theme

Date: 2026-06-05
Status: approved
Area: frontend (`recipe-assistant/frontend/src`)

## Goal

The user always runs Home Assistant in its default dark theme and wants the
add-on UI to look native inside HA — dark, matching HA's default-dark palette.
No light mode, no toggle, no system detection: the app is simply dark.

## Constraint discovered

The add-on is served through HA Ingress in an **iframe** (separate document), so
it cannot inherit HA's live theme CSS variables. We therefore **hardcode** HA's
default-dark tokens. If the user later switches HA to a non-default theme, the
add-on will not follow (out of scope).

## Palette (single dark theme in `src/main.tsx`)

```
mode: dark
primary.main   #03a9f4   (light #b3e5fc, dark #0288d1)   HA accent blue
secondary.main #ff9800                                    HA orange accent
background.default #111111   background.paper #1c1c1c
text.primary #e1e1e1   text.secondary #9b9b9b
divider rgba(225,225,225,0.12)
success #43a047   warning #ffa600   error #db4437   info #039be5
```

Also replace the two light hardcodes in the theme's component overrides:
- `MuiPaper` outlined border `#e0e0e0` → `theme.palette.divider`
- `MuiTableCell` head bg `#f5f5f5` → `theme.palette.action.hover`

## Non-theme-aware spots to fix (won't follow the palette automatically)

- **6 recharts charts** (`ConsumptionTrend`, `CategoryBreakdown`,
  `StorageLocations`, `TopConsumers`, `ProductDetail`, `RestockCostsWidget`):
  axis / grid / legend / tooltip text colours driven from `useTheme()`
  (`text.secondary`, `divider`). Series fill colours kept, lightened if too dark
  on `#111111`.
- **Widget backgrounds:** `RecentActivity` action colours, `ProductCard #fafafa`,
  `PersonsPage #f5f5f5/#e0e0e0`, `ProductDetailModal` → theme tokens.
- **Navbar** gradient: re-base on the HA blue so it sits on dark.

## Left as-is

- `ScanStationPage`: already purpose-built dark for the iPad kiosk.

## Verification

- `npm run build` (TypeScript typecheck passes).
- Run the app; Playwright screenshots of dashboard (charts), inventory, store to
  confirm a readable, native-HA-dark appearance.
- Styling is visual, not unit-tested; verified by build + screenshots.

## Follow-up

Bump `config.json` version before push (project convention).
