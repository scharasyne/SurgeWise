# Simulation Controls UX Implementation Plan

> Execute inline with superpowers:executing-plans and test-driven-development.

**Goal:** Implement the approved combined left controls and right results layout.

**Architecture:** Move the existing JSX into a persistent left aside. Preserve
state and request semantics, using CSS for the responsive layout and form entry.

**Tech Stack:** Existing Next.js, React, TypeScript, CSS and Node test tools.

**Spec:** ../specs/2026-11-14-simulation-controls-ux-design.md

## Global constraints

Preserve unrelated dirty files, scientific definitions, calculations, API
contracts and independent mode values. Use no new runtime dependencies. User
approved implementation in the existing new feature branch. Leave work unmerged.

## Review focus

- Mode tabs remain visible while settings scroll or playback is minimized.
- Rapid switching/loading never shows old-mode fields under a new mode.
- Right hospital inspection remains usable when the control form changes.
- Short and narrow screens retain a usable map, fields and Run action.
- Both reduced-motion sources disable the new animation.

### Task 1: Unified controls and mode semantics

**Files:** workspace component, workspace visibility tests, workspace CSS.

**Interfaces:** Existing QCControls/QCWorkspaceResult and sidebar contract.

- [x] Add React-tree tests for visible left ownership of tabs, playback and
  settings, plus right-only results and mode state persistence.
- [x] Run `node --test lib/workspace-visibility.test.mjs` from apps/web. Expect
  failure because controls are split and the mode tabs have hidden ancestry.
- [x] Move playback/settings into one left aside with persistent mode header,
  scrolling form, grouped disclosures and footer actions. Restrict right views
  to overview/hospitals, and move export to results. Format changed JSX clearly.
- [x] Update responsive CSS in place, including selected-tab styling and
  180 ms form entry disabled by system/manual reduced motion.
- [x] Rerun focused tests and `npm test`. Expect all checks to pass.

### Task 2: Verification and review

- [x] Run lint, TypeScript and production build from apps/web.
- [x] Use Playwright CLI for desktop, intermediate and mobile inspection,
  mode switching, scroll/focus and reduced motion where available.
- [x] Obtain read-only review of the scoped working diff. Address correctness
  findings and rerun affected checks.
- [x] Record exact evidence and remaining limits in session handoffs.

## Execution evidence

User approval covers this plan's design and inline implementation. Work remains
uncommitted for review. The vault session handoff is the progress ledger, as
required by repository instructions.

## Execution refinements

User clarified whole-panel minimization into a floating card and requested that
loading status stay inside controls to avoid shifting panels. Tests established
both missing behaviors before their implementation. Review identified async-form
entry timing and marker exclusion of the relocated overlay; both received
focused red/green verification. Browser inspection identified retained scroll
position and narrow-map padding, each corrected with regression coverage.
Application changes remain uncommitted for the user's review.
