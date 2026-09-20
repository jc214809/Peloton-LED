# Phase 6 implementation status

Phase 6 makes the screen rotation configurable and adds optional goals, durable milestones, scheduled brightness, and expanded 32-row workout details.

## Implemented

- `display.rotation` orders or removes named screen sections while preserving the prior rotation by default.
- `screen_durations` overrides timing by section. Total Workouts and lifetime pages share the `lifetime` duration, including the 3.2-second Bootcamp animation minimum.
- Weekly workout and minute progress is calculated from completed history since local Monday midnight.
- Optional lifetime Total Workouts thresholds generate one-time milestone screens. Acknowledgements persist in the private dashboard cache.
- Optional day/night brightness scheduling supports normal and overnight time ranges.
- A 32-row panel can show an optional second page of compatible workout statistics.
- Configuration is validated before hardware and network startup.

## Enable the optional features

The shipped examples keep weekly goals, milestones, brightness scheduling, and the second 32-row page disabled until values are chosen. Set positive weekly targets, add milestone thresholds, provide a brightness schedule, or set `compact_workout_pages` to `true` as needed.

## Validation boundary

Automated tests cover ordering, disabled sections, timing, weekly boundaries, durable acknowledgement, brightness boundaries, and rendering on both supported panel heights. Scheduled brightness and the two-page compact view still need visual acceptance on the physical matrix. Phase 5's Pi boot and Chromium acceptance run also remains outstanding.
