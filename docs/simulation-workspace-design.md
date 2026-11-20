# Map-first simulation workspace

User-approved implementation and refinements, 2026-11-16 (Asia/Manila).
This changes presentation and interaction; the engine, input bounds, approved
hospital network, source observations and API contracts are unchanged.

## Layout and interaction

- The simulation uses the dashboard's shared application rail, light palette,
  OpenFreeMap street/building context and hospital pins. No redundant page header.
- The initial view is a map and compact bottom playback dock. One optional right
  panel hosts Scenario, Results, barangay/hospital inspection or Layers. On phones
  this panel sits below the map. Results can be widened for tables and charts.
- In **Set up scenario**, choose Historical replay or Future forecast. Pick a start
  date and enter a duration from 1 to 28 days, or choose a duration preset.
  The final snapshot date updates as you edit. **Run simulation** applies the changes.
  A teal fill and checkmark identify the selected mode and duration.
- Historical replay offers saved forecast periods. Future forecast uses the month
  and day in the start date for seasonal planning. Both modes retain their own
  settings. Hospital planning groups capacity, admissions and length of stay
  separately from the choice of hospital.
- In **Future forecast**, **Projected dengue cases** offers a hypothetical surge with a multiplier, start delay and time to peak. The workspace leaves weather out of scenario setup and submits no weather override. Until the replacement case model is trained, the engine uses its existing default seasonal profile. Methods and the exported run retain the forecast provenance.
- In **Hospital planning**, Historical replay and Future forecast offer **Distance and preferred hospital** and **Distance only** with every overflow setting. Choose **Record the shortage at that hospital** or **Try the next most likely hospital with space**. The latter ranks available sites using the originating barangay’s selected probabilities. [First-admission and overflow methods](first-admission-matrix.md#using-the-chain-in-the-simulation)
- Under **Bed capacity**, both simulation modes use each hospital’s accredited bed count in the 30 September 2026 PhilHealth register as its fixed simulation total. Actual staffed capacity, occupancy and vacancies remain unknown. The default dengue reservation is 40% rounded to the nearest whole bed at each hospital. Other care receives the remainder. Across 46 hospitals this gives 3,756 dengue and 5,633 other-care beds.
- The starting assumption adds five temporary holding spaces at each hospital, two for dengue overflow and three for other care. Holding spaces are separate from the accredited bed stock and activated surge beds. The common holding total and the hospital-specific holding counts are editable.
- Choose a hospital to edit the division of beds or holding spaces. The total beside **Accredited beds** is read-only. Changing one side of the bed split assigns the balance to the other. **Use defaults** restores that hospital’s scenario settings.
- The repository contains the [46 initial allocations](../apps/web/public/data/qc-initial-bed-reservations.csv). **Download template** exports the current settings. CSV and XLSX imports use a facility ID or exact hospital name. If supplied, `accredited_beds` (legacy alias `staffed_beds`) and the sum of the split must match the registered total. An explicit split takes priority over the scenario percentage. Rows with only a matching total follow the percentage. Importing a valid file replaces hospital-specific values. Row errors prevent the entire import from applying.
- Playback retains play/pause, restart, previous/next day, speed, final-day jump
  and scrubbing. A peak-demand shortcut uses the backend's saved peak day; it is
  shown after playback starts. It never derives a competing peak in the browser.
  Since 2026-11-19 a small tab on the timeline's top edge hides the whole
  timeline (playback, readouts and Help) to give the map more room; a "Show
  timeline · Day N / total" tab stays at the bottom of the map to bring it back.
  Playback keeps running while it is hidden. Below 1100px the map credit and
  map tools sit slightly higher so the tab never covers them.
- Three compact readouts show accumulated projected cases with experimental
  range, current staffed beds required, and cumulative unplaced demand. Full day
  totals, observed source-year counts, holding, window totals, uncertainty and
  validation remain in Results. Historical observations are not current counts.
- Results retain the daily case chart, ranked annual candidates, local and city
  bed-demand curves, all-barangay table, same-input allocation comparison and
  methods/source details. Export has one entry point and still exports the same
  saved result JSON. Comparison opens its returned result at the final day.
- First use has a short hint instead of an automatically opened guide dialog.
  Help retains definitions and scientific caveats. The dialog traps focus and
  stays inside fullscreen. Native fullscreen has an in-app fallback and keeps the
  timeline and optional inspector accessible while excluding the global rail.

## Inspector refinement

Barangay cases, annual ranking, nearest hospital and local hospital matches are
separate sections. Plain names are separated from explicit Inspect actions.
Aligned definition lists replace mixed inline buttons and oversized bold text.
The three hospitals with the highest modeled first-admission probabilities each have
an expandable card showing their share and straight-line distance. Registered inventory is distinct
from scenario capacity, both occupancy denominators, holding, daily demand and
window peaks. Source links and the complete hospital selector remain available.
The selected barangay's arrival split and attributed demand stay in a disclosure;
they are not conflated with hospital-wide utilization or real vacancies.

## Map semantics

The existing numeric case bands and fixed-window scale remain unchanged, with a
monotonically darker yellow-green/olive/ochre/orange/burnt-orange ramp. These are
case counts, not official risk thresholds. Neutral polygons may still have cases.
The numbered markers identify the annual predicted-burden ranking, not cases or
confirmed weekly outbreaks. Optional connections preserve proximity versus
modeled placement meanings. The initial map has no connection network; selecting
a place reveals its relevant links. The optional all-connections layer remains
available in Layers.

Dashboard and Simulation now call the same hospital-marker factory and use one
shared style and SVG. The H pin is a provisional inventory point on both
pages; Simulation adds assumed demand and capacity in its inspector. The pin's
outer white border is removed. Both pins and numbered markers breathe subtly;
motion is purely cosmetic and has no live-status or disease-spread meaning.
Hover/focus pauses the pulse; OS reduced motion and the simulation's manual
reduced-motion setting disable it.

Duplicate red/green source halos are invisible. Hover/focus shows labels only.
Overlap guides and extra coordinate dots are removed, including on selection. Marker containers use
MapLibre absolute positioning; inner rank symbols fill their square containers,
remaining circular rather than inheriting a content-sized grid track. When a
hospital is inspected, small unnumbered symbols identify additional linked
barangay origins; they do not acquire a top-ten annual rank. Selected boundaries are 1.2px, with a
small decorative lift instead of the former thick outline and tall extrusion.
This decorative height is not a measured building or disease quantity.

3D generalized OSM buildings, QC/Philippines camera views, an optional national
locator, hospital pins, connection toggles and reduced motion are in Layers.
An optional Satellite imagery layer (since 2026-11-19) shows Esri World Imagery
under roads and labels, like a hybrid map: minor roads, rails, casings and flat
buildings are hidden, major roads are highlighted, and labels turn light with
dark halos. Neutral barangays become a faint veil over it; case-colored ones keep
their colors. Imagery capture dates vary by place, so it is dated background, not
current conditions, and it does not verify hospital entrances. Esri is credited
in the map attribution while the layer is visible. Dashboard has no imagery. The national locator mounts on expansion and
resizes with its container. Camera padding accounts for top controls without
treating a wide status banner as a left sidebar.

## Directional inspection and camera focus

Barangay inspection shows the three nearest sites supplied by the engine plus
mapped hospitals inside that barangay. Hospital inspection shows incoming links
from ranked nearby barangays, its nearest ranked context and actual saved-day
modeled placements involving that hospital. Zero/missing placements and unknown
IDs produce no placement line. Arrow direction always follows barangay to
hospital; clicking the hospital does not reverse the modeled relationship.

Selected links reveal outward over 650ms and use moving chevrons. Dashed teal is
straight-line proximity, solid teal is a saved modeled placement, solid ochre
includes holding placements, and dashed ochre is nearest-ranked context. A saved
placement supersedes the proximity decoration on the same endpoint pair. SVG
endpoints follow the displayed markers, including screen-space overlap offsets;
underlying geographic coordinates are not changed. The optional all-connections
view uses this same renderer; there is no second set of source-to-source lines. Repeated clicks replay the
reveal. Playback updates saved-day placements without restarting the common
motion clock. Reduced motion uses full static lines and directional chevrons,
without scheduling animation frames. Cleanup removes frames and map listeners.

Selecting a barangay shows all 46 first-admission arrows by default, including
at day zero. The inspector’s hospital name search works with the arrows shown
or hidden. With the arrows enabled, wheel and pinch gestures over
a barangay-to-hospital arrow zoom the map. Hover, tap or keyboard focus on the
arrow opens its probability breakdown. Escape dismisses the breakdown.

Each explicit inspection starts an 850ms map transition to the selected network.
Bounds include every displayed connected endpoint and, for barangay inspection,
the complete source boundary. Padding accounts for the resized map and overlays;
zoom is capped at 14.5. A new selection interrupts the previous transition. The
camera reads the saved day at the click and does not refocus on day changes.
Reduced motion makes the transition immediate. The existing Reset map view
control returns to QC/Philippines context. Nothing calculates a travel route or
new patient-flow result in the browser.

## Opening and legend consistency

See `workspace-loading-design.md`. Simulation and Dashboard reuse the centered,
pulsing SurgeWise logo while their initial maps prepare. Simulation fits the
complete official QC geometry and resizes before marker construction, then
reveals the map on idle. The opening extent no longer depends on scenario
response timing. Markers are initially hidden until their offsets are assigned;
the initial cohort fades once. No context-arrival camera refit or hover guide
line is drawn. Actual source coordinates are unchanged.

`SIMULATION_LINES` defines the exact renderer and legend colors/dash styles.
Legend entries include annual rank, the hospital pin (provisional point, location not verified), unranked
linked/selected barangays, neutral polygons, selected outline, proximity,
saved-day placements, holding and nearest-ranked context. Placement entries are
withheld at day zero. An expansion-boundary entry appears only for a saved
expansion ring. No mapped-point guide entry remains because those guides are
removed. A held placement means that some placements use holding; pins never
encode verified vacancies or eligibility.

## Validity and verification

Editing inputs cancels pending requests, resets playback and clears result values.
Annual candidate markers from the old run are withheld until new data loads.
Mode switching restores the corresponding edited form. Late responses are
discarded. Day zero still hides projected values, hospital forecasts and exports;
the inventory and candidate-location preview remain distinct. Missing data never
becomes a manufactured zero or an unguarded simulation run.

The active network remains 46 PhilHealth QC records and 9,389 accredited beds,
with all entrances unverified. Staffed/dengue capacity and eligibility are
assumptions; allocation distance is a provisional straight-line proxy.

Tests cover data gating, request cancellation, independent modes, panel layout,
preserved inputs/export, combobox keys, camera exclusions, MapLibre style
validity, continuous colors and their lightness ordering, and shared accessible
hospital symbols, directional connection membership, saved-placement gating,
SVG endpoint/direction/timing/cleanup, and the actual selection-camera effect.
Local software-graphics browser checks have confirmed round markers, both
inspection modes, directional arrow movement and a clean browser error log.
Consult the session handoff for the latest executed checks and their limits.
