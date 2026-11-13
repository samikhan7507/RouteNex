# UI system

The v3 frontend is a light, accessible React SPA (React 19 + Vite) with a calm navy/white theme.

## Routes & guards
| Path | Page | Roles |
|---|---|---|
| `/login` | Login (email / phone OTP) | public |
| `/` | Home overview | all signed-in |
| `/shop` | Catalogue, basket, checkout | customer/admin |
| `/trips` | Ride & parcel booking | customer/admin |
| `/orders` | Order history & detail | customer/admin |
| `/wallet` | Wallet, top-up, offers | customer/admin |
| `/driver` | Requests, trips, deliveries, earnings | driver |
| `/operations` | Optimizer, alerts, events, forecast, ML | dispatcher/fleet_manager/admin |
| `/fleet` | Vehicles, drivers, maintenance | fleet_manager/admin |
| `/admin` | Sessions, users, audit, payments, catalogue, settlements | admin |
| `/settings` | Profile, password, devices | all signed-in |

## Shared components (`src/components/`)
- `ui.jsx` — Button, Card, Badge, Field, Modal, Empty, ErrorBox, Loading, Stat, Table, Tabs, `useAsync`.
- `PlaceSearch.jsx` — 300 ms debounced combobox backed by `/places/search`; keyboard navigable.
- `MapView.jsx` — react-leaflet map, fit-bounds, click-to-pin, OSM tiles.
- `PaymentModal.jsx` — demo simulate success/failure vs Razorpay Checkout + verify.
- `Layout.jsx` — role navigation, 30 s notification polling, mark-read.
- `Assistant.jsx` — propose → confirm → execute; never auto-runs actions.

## Conventions
- API client (`src/api.js`) sends cookies, attaches CSRF to mutations, and refreshes an expired CSRF
  token once before retrying.
- Money is formatted with `money()` (en-IN); statuses are humanised with `titleCase()`.
- Idempotency keys use `crypto.randomUUID()`.
- Demo-only affordances (demo OTP notices, simulated payment buttons) render only when the API says
  demo mode is enabled.
- The PWA service worker caches the shell/static assets only; API responses are never cached.

## Styling
`src/styles.css` defines the design tokens and the class vocabulary used across pages
(`.card`, `.stat-grid`, `.product-grid`, `.booking-grid`, `.timeline`, `.otp-box`, `.modal`, etc.),
with responsive breakpoints at 1024 px and 760 px and a reduced-motion fallback.
