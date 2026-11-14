# RouteNex UI system

The redesigned shell uses a full-width content canvas (`calc(100% - sidebar)`), fluid page gutters, reusable card/table/form primitives and responsive CSS Grid. Breakpoints are 1180px (dashboard reflow), 860px (compact sidebar) and 590px (single-column mobile).

## Experiences
- **Customer:** simplified commerce, cart, delivery tracking and ride booking with low-density KPIs and clear actions.
- **Operations/Admin:** denser enterprise KPIs, manifests, audit visibility, alert controls, fleet state, analytics and optimizer workflow.

## Optimizer workflow
1. Select eligible pending orders.
2. Select available capacity and driver-linked vehicles.
3. Choose strategy and traffic multiplier.
4. Generate persisted routes and monitor the route manifest.
5. Trigger incidents for audited dynamic release and reassignment.

Maps use a large offline-safe route canvas so the app remains functional without third-party keys. The geometry, stop, ETA and vehicle fields are ready for a Google Maps or Mapbox renderer in production.

Tables are placed in horizontal overflow containers on narrow screens. Forms and KPI grids collapse progressively; navigation becomes an icon rail. All controls include focus styling, consistent touch targets and loading/error feedback.