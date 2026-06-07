# Navbar Refresh Button — Design

**Date:** 2026-06-07
**Status:** Approved

## Goal

Add a refresh button to the top-right of the navbar that re-fetches the data
on the page the user is currently looking at (e.g. on the Picnic page: cart +
orders + offers; on Inventory: the inventory list). Refreshing should give
honest visual feedback (spinning icon while in flight) and avoid a full page
reload, so tab/scroll state is preserved.

## Background

The frontend has no global data store (no React Query). Each page composes its
own hooks (`usePicnicCart`, `usePicnicPendingOrders`, `useInventory`, etc.), and
each hook holds local `useState` and exposes its own `refetch()`. The `Navbar`
lives at the app level (`App.tsx`), separate from the routed pages, so it has no
direct access to page-level `refetch` functions. The design bridges that gap.

## Approach

**Refresh registry via React context.** A `RefreshProvider` keeps a set of
registered async refetch functions. Pages opt in by registering their refetch
function(s) on mount and unregistering on unmount. The navbar button awaits all
*currently registered* callbacks — because only the mounted (current) page's
callbacks are registered, this naturally scopes the refresh to the current page
and yields a real "done" signal for the spinner.

Rejected alternative — a refresh counter that every data hook adds to its
`useEffect` deps: requires editing every hook and gives no clean completion
signal for the loading state.

## Components

### `RefreshProvider` (new — `components/RefreshProvider.tsx`)
- Holds a `Set<() => Promise<unknown> | unknown>` of registered refetch fns in a
  ref (registration must not trigger re-renders).
- Exposes via context:
  - `register(fn): () => void` — adds `fn`, returns an unregister function.
  - `refreshAll(): Promise<void>` — snapshots the current set and awaits all fns
    in parallel (`Promise.allSettled`, so one failing refetch does not block the
    others).
  - `refreshing: boolean` — true while `refreshAll()` is in flight.
  - `canRefresh: boolean` — true when at least one fn is registered.
- `canRefresh` is reactive state (so the navbar button can enable/disable),
  updated whenever the registry size changes.
- Wraps the app inside `NotificationProvider` in `App.tsx`.

### `useRegisterRefresh(fn)` hook (in the same file)
- Registers `fn` on mount, unregisters on unmount.
- Wrap the page's refetch logic in `useCallback` so the registration effect is
  stable; the hook depends on the provided `fn`.

### `Navbar` (edit)
- Add an `IconButton` with `RefreshIcon` after the title `Typography` (which
  already has `flexGrow: 1`, pushing the button to the right edge).
- While `refreshing`: apply a CSS rotation animation to the icon and disable the
  button. When `!canRefresh`: disabled (greyed out).
- `onClick` calls `refreshAll()`.

## Page wiring

- **PicnicStorePage** (primary target): register a single combined callback that
  runs `cartRefetch`, `ordersRefetch`, and the offers refetch in parallel.
- **DashboardPage** and **InventoryPage**: register their existing `refetch`
  (both hooks already expose one) so the button works there too. Cheap to add.
- Other pages may register later; until they do, the button is simply disabled
  on those pages.

## Behavior

1. User clicks refresh → icon spins, button disabled.
2. All registered refetch fns run in parallel via `Promise.allSettled`.
3. Spin stops, button re-enabled.
4. A single failing refetch does not abort the others (settled, not all).
5. Button is visible on every navbar page; disabled when the current page
   registered nothing. (The navbar is already hidden on `/scan-station`.)

## Testing

Frontend has no existing component test harness, so verification is manual:
- Picnic page: change cart on the Picnic app (or via another tab), click
  refresh, confirm cart/orders/offers update without a full reload.
- Confirm the icon spins while refreshing and the button disables, then
  re-enables.
- Navigate to a page that registers nothing → button is disabled.

## Out of scope

- Auto-refresh / polling.
- A global "refresh everything regardless of page" mode.
- Per-section refresh buttons within pages.
