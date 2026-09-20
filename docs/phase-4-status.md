# Phase 4 implementation status

Phase 4 makes the display useful during restarts and connectivity failures, and prevents personal-record celebrations from replaying indefinitely.

## Implemented

- Every successful refresh atomically writes the display snapshot to a versioned JSON cache.
- The default cache is `dashboard-cache.json` beside the token; `display.cache_path` can override it.
- Cache files and temporary replacements use owner-only `0600` permissions.
- Startup loads a valid cache before starting the network worker, so workout and overview screens are immediately available offline.
- Invalid JSON, unsupported versions, and structurally invalid caches are ignored without blocking startup.
- A blue clock in the bottom-left marks cached or retained data until a live refresh succeeds.
- The blue stale clock appears only after three consecutive refresh failures; a successful refresh resets it. It and the amber login padlock can appear together without overlap.
- A PR celebration is acknowledged only after its screen is shown. The last 256 acknowledged workout IDs are stored in the same cache, preventing replays across rotations and restarts while keeping state bounded.
- Cache write failures do not replace valid in-memory data or stop the display.

## Acceptance evidence

- Tests restart a dashboard from disk with the Peloton client offline and verify that the prior complete snapshot remains available.
- Cache permissions, corrupt-cache rejection, schema/version rejection, and live-success stale-state clearing are covered.
- Both 32-row and 64-row displays render the stale clock in the bottom-left while retaining the login indicator in the bottom-right.
- Tests verify that a PR screen follows its workout, appears once across multiple rotations, and stays acknowledged after restart.

## Remaining roadmap

- Goals and milestone celebrations.
- Configurable screen ordering and enable/disable controls.
- Scheduled brightness and quiet hours.
- Installer-managed services, including optional automatic token maintenance.
