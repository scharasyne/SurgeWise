# Simulation controls UX — proposed design

Status: approved and implemented, 2026-11-14, Asia/Manila.
Branch: `feat/simulation-controls-ux`, based on `feat/light-theme` at
`ae1d8124dbe491f0e2b85c919da0033949b89911`.

## User requirements

Combine simulation settings and playback controls in the left panel. Reserve the
right panel for simulation results and hospital capacity. Historical replay and
Future surge forecast must remain visible, with emphasis on the selected mode.
Switching modes should smoothly reveal the appropriate form. Keep the existing
light-theme visual language and accommodate nontechnical users with concise,
relevant labels.

This is a presentation change. Forecast methods, numerical outputs, scientific
labels, supported dates, saved scenario contracts and source artifacts retain
their existing behavior. Previously rejected local weekly weather forecasting
ideas are outside this request.

## Approaches

1. **One left control panel — recommended.** A persistent mode header, compact
   playback, grouped form and persistent Run action share one panel. Advanced
   fields use disclosures. This keeps setup and playback discoverable, with a
   longer scrolling form as the tradeoff.
2. **Setup and Playback subviews.** A second selector below the mode tabs swaps
   between settings and playback. This is shorter but requires additional
   navigation and hides related controls.

The Master Plan Architect recommends the first approach. The recommendation is
a design judgment approved by the user before implementation.

## Layout and interaction

### Left controls

- Keep the full Historical replay and Future surge forecast names in a fixed
  header above the panel's scrolling body. Allow text wrapping. Emphasize the
  selected mode through its fill and selected-state semantics.
- Keep compact playback near the top of the body, including date/day, slider,
  Play/Pause and Final day. Preserve previous/next/restart/speed controls and
  playback minimization. Minimizing playback must leave both mode tabs visible.
- Group settings in this order: Dates, Scenario, Hospital assumptions, Map
  display, then existing source/model evidence. Keep dates and relevant scenario
  choices readily available. Advanced hospital fields, display options and
  evidence use collapsed disclosures.
- Keep Run simulation available in the panel's action footer. Preserve the
  existing baseline-versus-optimized comparison action as secondary.
- Keep existing quick-horizon immediate-run behavior and its explanation.
  Ordinary field edits continue to require Run.

### Map and right results

- Give the map the remaining center region instead of covering it with a second
  playback/settings overlay.
- Keep right-panel overview and hospital inspection, including their current
  selection behavior, capacity definitions and daily/window distinctions.
- Move export to the results area.
- Remove right-panel settings navigation and update guide text to point to the
  left controls.
- Keep the right panel's existing collapse/reveal and resize behavior unless
  responsive verification establishes a necessary small adjustment.

### Mode transition

Use one active form with a roughly 150–200 ms opacity/vertical-entry animation.
Mode selection updates immediately. Both the operating-system reduced-motion
preference and the existing reduced-motion control disable this animation.
Retain keyboard Arrow/Home/End mode switching, focus on the selected tab,
independent form values per mode, cancellation and stale-response protection.
Loading/failure preserves the mode header and shows a local status in the form
region. No old-mode form or results appear under the newly selected mode.

### Responsive behavior

- Wide screens use left controls, center map and right results. Target an
  approximately 300–320 px left panel with a useful map minimum.
- Intermediate widths place controls beside the map and results below when
  three columns would make the map too narrow.
- Mobile uses one form instance in the order mode controls, settings/playback,
  map and results. Keep the mode row reachable through a sticky header and avoid
  covering focused fields. Verify long labels and 320 px width.

## Acceptance criteria

1. Both mode tabs are visible in the left panel in overview, hospital inspection,
   loading, error and minimized-playback states.
2. Exactly one mode is selected, with correct tab/form linkage and keyboard use.
3. All scenario inputs and playback controls share the left region. Right
   results contain no scenario-editing form or duplicate controls.
4. Returning to a mode restores its independently edited settings.
5. Rapid mode changes abort earlier requests and reject late responses. Editing
   settings invalidates previous results and resets playback.
6. Day-zero concealment, final-day behavior, hospital inspection, export gating
   and scientific/assumption labels retain their existing meaning.
7. Entry motion is smooth and absent under reduced motion. Focus remains usable.
8. Desktop, intermediate, short-height and narrow-mobile layouts keep mode
   selection and actions usable without horizontal page overflow.

## Implementation scope and verification

Expected application files are `components/qc-simulation-workspace.tsx`,
`app/outbreak-response/qc-simulation.css` and focused tests under `apps/web/lib/`.
An ordinary left aside can avoid changes to the shared sidebar component.
Resolve existing late two-column CSS overrides in place.

Before application edits, add focused tests with the repository's existing React
render/tree harness and demonstrate the missing layout behavior. Verify actual
ownership and hidden ancestors, rather than searching only rendered text.
Then run the focused checks, full frontend tests, lint, TypeScript and production
build. Browser inspection should cover responsive layout, keyboard mode changes,
scrolling and reduced motion.

Baseline run on this branch: `npm test` from `apps/web` passed all 13 test files.
No application changes or new acceptance tests have been made yet. The
in-conversation mockup demonstrates proposed mode switching and preserves its
sample form fields; it executes no simulation. Its JavaScript syntax and element
references were checked. Browser rendering remains unverified.

## Implementation refinements requested during execution

The user clarified that minimizing must turn the entire dock into a compact
floating card over the map. Both modes and compact playback remain available;
expanding restores the settings. Loading and error messages live within the
left header, keeping the map/results top position stable. The floating card is
included in map marker exclusion and narrow-screen fit padding is bounded.

Implementation uses the existing controls state and APIs. Changed JSX/CSS/tests
were formatted with pinned temporary Prettier 3.6.2 without project dependency
changes. Final test evidence is recorded in docs/SESSION_HANDOFF.md.
