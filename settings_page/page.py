"""The settings page's HTML: the form for config.json (fields named as form.apply_form reads
them), the PIN page, and the notices after a save. Everything is inline (styles, icons, a few
lines of script), since a phone on the Wi-Fi setup hotspot has no internet to fetch anything
from. It works without JavaScript; the script adds dragging and moving screens in the rotation
(a switched-off one drops to the bottom) and the "unsaved changes" state. No secret is ever put on it: logins and Pushover keys stay in auth.env.
"""
from html import escape
from zoneinfo import available_timezones

from peloton.config import DEFAULTS, GPIO_MAPPINGS, MATRIX_DEFAULTS
from settings_page.logins import when
from settings_page.form import (COLORS, FONTS, FORM_FIELD, PANEL_FIELDS, PANEL_SIZES, ROTATIONS, SCREENS,
                                SHARED_DURATION, STREAK_REMINDER_DEFAULT, SWITCH_KEYS, TIMING, WEEKDAYS,
                                advanced_keys, duration_fallback, milestones_text, number_text, panel_size,
                                riders, rotation_rows, section)

# What a save says, by Settings.restart_app's outcome.
SAVED = ('restarted', 'not_running', 'saved', 'failed')
# What the Logins card says after its buttons, by Settings' outcome: (kind, text).
LOGIN_OUTCOMES = {
    'logins_saved': ('good', '<strong>Logins saved</strong> to auth.env. Renewal uses them from its next run; '
                             '<em>Renew now</em> tries straight away.'),
    'logins_unchanged': ('info', 'Nothing to save: every login field was blank, so the saved ones stay.'),
    'renew_started': ('good', '<strong>Renewal started.</strong> It takes a few seconds, or a few minutes with '
                              'a browser login: reload the page to see how it went.'),
    'renew_running': ('warn', 'Renewal is already running: reload the page in a minute.'),
    'renew_failed': ('bad', "Renewal couldn't be started; the settings page's log says why."),
    'renew_unavailable': ('warn', 'Renewal can only be started on a board (it runs under systemd).'),
    'test_sent': ('good', 'Test alert sent: check your phone.'),
    'test_wait': ('warn', 'A test alert went out less than a minute ago.'),
    'test_failed': ('bad', "Pushover didn't take the test alert: check the keys (the log says why)."),
    'test_off': ('warn', 'Set both Pushover keys below first.'),
}
SENT = ('sent', 'wait', 'used', 'failed')  # pins.PinGate.send_pin's outcomes

STYLE = """
:root {
  --bg: #f4f5f7; --surface: #fff; --surface-2: #f8f9fb; --border: #e3e6eb; --border-strong: #cfd4dc;
  --text: #111827; --text-2: #4b5563; --text-3: #6b7280;
  --accent: #2f54eb; --accent-hover: #2546c9; --accent-soft: #e8edff; --on-accent: #fff;
  --good: #067647; --good-bg: #ecfdf3; --good-line: #abefc6;
  --bad: #b42318; --bad-bg: #fef3f2; --bad-line: #fecdca;
  --warn: #93370d; --warn-bg: #fffaeb; --warn-line: #fedf89;
  --shadow: 0 1px 2px rgba(16, 24, 40, .05), 0 1px 3px rgba(16, 24, 40, .06);
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) { :root {
  --bg: #0b0d12; --surface: #141821; --surface-2: #1a1f2a; --border: #262c38; --border-strong: #3a4252;
  --text: #eef1f6; --text-2: #b4bccb; --text-3: #8b94a5;
  --accent: #6b8cff; --accent-hover: #8aa4ff; --accent-soft: #1c2440; --on-accent: #0b0d12;
  --good: #75e0a7; --good-bg: #0c2a1c; --good-line: #14532d;
  --bad: #fda29b; --bad-bg: #2d1412; --bad-line: #5c1f1a;
  --warn: #fec84b; --warn-bg: #2b2110; --warn-line: #5c4313;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4);
} }
* { box-sizing: border-box; }
html { scroll-padding-top: 84px; }
body { margin: 0; background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased;
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round; flex: none; }
h1, h2, h3, p { margin: 0; }
a { color: var(--accent); }

/* Top bar */
.topbar { position: sticky; top: 0; z-index: 20; background: var(--surface); border-bottom: 1px solid var(--border); }
.topbar-in { max-width: 1080px; margin: 0 auto; padding: 0 16px; height: 60px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.mark { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(135deg, #df1c2f, #8b1020); box-shadow: var(--shadow); flex: none; }
.mark svg { width: 18px; height: 18px; }
.brand-name { font-weight: 650; letter-spacing: -.01em; white-space: nowrap; }
.brand-sub { color: var(--text-3); font-size: 12.5px; }
.top-meta { display: flex; align-items: center; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text-2); font-size: 13px;
  font-weight: 500; white-space: nowrap; }
.chip svg { width: 14px; height: 14px; }
.chip.warn { color: var(--warn); background: var(--warn-bg); border-color: var(--warn-line); }
.chip.good { color: var(--good); background: var(--good-bg); border-color: var(--good-line); }
.topbar form { margin: 0; }
.topbar button { height: 28px; padding: 0 10px; font-size: 13px; }
@media (max-width: 520px) { .brand-sub, .chip.board { display: none; } }

/* Layout */
.shell { max-width: 1080px; margin: 0 auto; padding: 28px 16px 128px; display: grid; gap: 32px; }
@media (min-width: 960px) { .shell { grid-template-columns: 200px minmax(0, 1fr); } }
.toc { display: none; }
@media (min-width: 960px) {
  .toc { display: block; position: sticky; top: 88px; align-self: start; }
  .toc a { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 8px;
    color: var(--text-2); text-decoration: none; font-weight: 500; font-size: 14px; }
  .toc a:hover { background: var(--surface); color: var(--text); }
  .toc a.on { background: var(--accent-soft); color: var(--accent); }
  .toc svg { width: 16px; height: 16px; }
}
.page-head { margin-bottom: 20px; }
.page-head h1 { font-size: 24px; font-weight: 700; letter-spacing: -.02em; }
.page-head p { color: var(--text-2); margin-top: 4px; }
.stack { display: grid; gap: 20px; }

/* Cards */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); }
.card-head { display: flex; gap: 14px; align-items: flex-start; padding: 18px 20px; border-bottom: 1px solid var(--border); }
.card-icon { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: var(--accent-soft); color: var(--accent); flex: none; }
.card-head h2 { font-size: 16px; font-weight: 650; letter-spacing: -.01em; }
.card-head p { color: var(--text-3); font-size: 13.5px; margin-top: 2px; }
.card-body { padding: 4px 20px 18px; }
details.card > summary { list-style: none; cursor: pointer; border-bottom: 0; border-radius: 14px; }
details.card > summary::-webkit-details-marker { display: none; }
details.card[open] > summary { border-bottom: 1px solid var(--border); border-radius: 14px 14px 0 0; }
.chev { margin-left: auto; align-self: center; color: var(--text-3); transition: transform .15s; }
details[open] .chev { transform: rotate(180deg); }
.card-body h3 { font-size: 12px; font-weight: 650; text-transform: uppercase; letter-spacing: .06em;
  color: var(--text-3); margin: 22px 0 4px; }

/* Fields */
.field { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 6px 28px;
  padding: 16px 0; border-top: 1px solid var(--border); align-items: start; }
.card-body > .field:first-child, .card-body > h3 + .field, .notice + .field { border-top: 0; }
.field.inline { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
.field-label label, .label { font-weight: 550; display: inline-block; }
.hint { color: var(--text-3); font-size: 13px; margin-top: 3px; }
.label-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
@media (max-width: 640px) { .field { grid-template-columns: 1fr; } .field.inline { grid-template-columns: 1fr auto; } }
input[type=text], input[type=email], input[type=password], input[type=number], input[type=date], input[type=time], select {
  width: 100%; height: 40px; font: inherit; color: var(--text); background: var(--surface);
  padding: 0 12px; border: 1px solid var(--border-strong); border-radius: 8px;
  transition: border-color .15s, box-shadow .15s; }
input::placeholder { color: var(--text-3); }
select { appearance: none; padding-right: 34px; background-repeat: no-repeat; background-position: right 11px center;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%238b94a5' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E"); }
input:hover, select:hover { border-color: var(--text-3); }
input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.unit { position: relative; display: block; }
.unit input { padding-right: calc(20px + var(--u, 1) * 1ch); -moz-appearance: textfield; appearance: textfield; }
.unit input::-webkit-outer-spin-button, .unit input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.unit-text { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); color: var(--text-3);
  font-size: 13.5px; pointer-events: none; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; }
.pair { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: center; }
.pair span { color: var(--text-3); font-size: 13px; }
.below { margin-top: 8px; }
.buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 999px; font-size: 12px;
  font-weight: 550; background: var(--surface-2); color: var(--text-3); border: 1px solid var(--border); }
.pill.ok { color: var(--good); background: var(--good-bg); border-color: var(--good-line); }
.pill svg { width: 12px; height: 12px; }

/* Switches */
.switch { appearance: none; margin: 0; width: 42px; height: 24px; border-radius: 999px; position: relative;
  background: var(--border-strong); cursor: pointer; transition: background .15s; flex: none; }
.switch::after { content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .3); transition: transform .15s; }
.switch:checked { background: var(--accent); }
.switch:checked::after { transform: translateX(18px); }
.switch:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--accent-soft), 0 0 0 1px var(--accent); }

/* Buttons */
button, .btn { font: inherit; font-weight: 600; display: inline-flex; align-items: center; justify-content: center;
  gap: 8px; height: 40px; padding: 0 16px; border-radius: 9px; cursor: pointer; border: 1px solid transparent;
  transition: background .15s, border-color .15s; }
.primary { background: var(--accent); color: var(--on-accent); box-shadow: var(--shadow); }
.primary:hover { background: var(--accent-hover); }
.primary:disabled { opacity: .7; cursor: progress; }
.secondary { background: var(--surface); color: var(--text); border-color: var(--border-strong); box-shadow: var(--shadow); }
.secondary:hover { background: var(--surface-2); }
.ghost { background: transparent; color: var(--accent); padding: 0 10px; }
.ghost:hover { background: var(--accent-soft); }
button:focus-visible, summary:focus-visible, a:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--accent-soft), 0 0 0 1px var(--accent); }
.block { width: 100%; }

/* Notices */
.notice { display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border-radius: 10px;
  border: 1px solid; margin-bottom: 16px; font-size: 14px; }
.notice svg { margin-top: 1px; }
.notice ul { margin: 4px 0 0; padding-left: 18px; }
.notice.good { color: var(--good); background: var(--good-bg); border-color: var(--good-line); }
.notice.bad { color: var(--bad); background: var(--bad-bg); border-color: var(--bad-line); }
.notice.warn { color: var(--warn); background: var(--warn-bg); border-color: var(--warn-line); }
.notice.info { color: var(--text-2); background: var(--surface-2); border-color: var(--border); }
.notice.info svg { color: var(--accent); }
.card-body > .notice { margin: 16px 0 0; }

/* Save bar */
.savebar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 90%, transparent); backdrop-filter: saturate(1.4) blur(10px); }
.savebar-in { max-width: 1080px; margin: 0 auto; padding: 12px 16px; display: flex; align-items: center;
  justify-content: space-between; gap: 16px; }
.status { display: flex; align-items: center; gap: 8px; color: var(--text-3); font-size: 13.5px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--good); flex: none; }
.status.dirty { color: var(--text); font-weight: 550; }
.status.dirty .dot { background: #f79009; }

/* Sign-in and message pages */
.center { min-height: calc(100vh - 60px); display: grid; place-items: center; padding: 32px 16px; }
.auth { width: 100%; max-width: 420px; padding: 28px; }
.auth-icon { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; margin-bottom: 18px;
  background: var(--accent-soft); color: var(--accent); }
.auth-icon svg { width: 24px; height: 24px; }
.auth h1 { font-size: 21px; font-weight: 700; letter-spacing: -.02em; }
.auth > p { color: var(--text-2); margin: 6px 0 22px; }
.step { display: flex; gap: 12px; padding: 16px 0; border-top: 1px solid var(--border); }
.step-n { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; flex: none;
  background: var(--surface-2); border: 1px solid var(--border-strong); font-size: 12.5px; font-weight: 650; color: var(--text-2); }
.step-body { flex: 1; min-width: 0; }
.step-body p { color: var(--text-3); font-size: 13.5px; margin: 2px 0 12px; }
input.pin { height: 56px; text-align: center; font-size: 26px; font-weight: 650; letter-spacing: .5em;
  padding-left: .5em; font-variant-numeric: tabular-nums; margin-bottom: 12px; }

/* Schedules */
.schedule { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 4px 0 8px; }
.schedule.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.schedule-wrap[hidden] { display: none; }
.schedule-note { margin: 0 0 10px; }
@media (max-width: 640px) { .schedule, .schedule.three { grid-template-columns: 1fr 1fr; } }
.mini { display: block; font-size: 12.5px; font-weight: 550; color: var(--text-2); margin-bottom: 5px; }

/* Rotation: one row per screen, numbered in the order the board shows them */
.screens { list-style: none; margin: 0; padding: 8px 0 0; counter-reset: screen; }
.screen-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) 7.5em auto auto; gap: 8px 14px;
  align-items: center; padding: 12px 0; border-top: 1px solid var(--border); }
.screen-row:first-child { border-top: 0; }
.screen-row::before { content: ""; width: 24px; height: 24px; }
.screen-row.on { counter-increment: screen; }
.screen-row.on::before { content: counter(screen); border-radius: 50%; display: grid; place-items: center;
  background: var(--accent); color: var(--on-accent); font-size: 12px; font-weight: 650; }
.screen-row:not(.on) .screen-name { color: var(--text-3); }
.screen-name { font-weight: 550; }
.screen-row .shared { color: var(--text-3); font-size: 13px; }
.move { width: 32px; height: 32px; padding: 0; border-radius: 8px; background: transparent; color: var(--text-3); }
.move:hover { color: var(--accent); background: var(--accent-soft); }
.move svg { width: 16px; height: 16px; }
.screen-row:first-child .move, .screen-row:not(.on) .move, .screen-row:not(.on) .grip { visibility: hidden; }
/* With the script: a grip on the left of each row, dragged by mouse or finger (pointer events). */
.screens.js .screen-row { grid-template-columns: 24px 28px minmax(0, 1fr) 7.5em auto auto; }
.grip { order: -1; width: 24px; height: 32px; padding: 0; border-radius: 6px; background: transparent;
  color: var(--text-3); cursor: grab; touch-action: none; }
.grip:hover { color: var(--accent); background: var(--accent-soft); }
.grip svg { width: 16px; height: 16px; }
.screen-row.dragging { background: var(--accent-soft); border-radius: 10px; box-shadow: var(--shadow); }
.screen-row.dragging .grip { cursor: grabbing; }
body.dragging { user-select: none; -webkit-user-select: none; cursor: grabbing; }
@media (max-width: 640px) { .screen-row { grid-template-columns: 24px minmax(0, 1fr) auto auto; }
  .screens.js .screen-row { grid-template-columns: 24px 24px minmax(0, 1fr) auto auto; }
  .screen-row .time { grid-column: 2 / -1; } .screens.js .screen-row .time { grid-column: 3 / -1; } }

/* Riders */
.rider { padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); margin-top: 12px; }
.rider > .hint { margin: -4px 0 12px; }
.rider h3 { margin: 0 0 10px; text-transform: none; letter-spacing: 0; font-size: 15px; color: var(--text); }
.login { padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2);
  margin-top: 12px; display: grid; gap: 6px; }
.login-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.login-head strong { font-size: 15px; }
.login .hint { margin: 0; }
.pill.bad { color: var(--bad); background: var(--bad-bg); border-color: var(--bad-line); }
.pill.warn { color: var(--warn); background: var(--warn-bg); border-color: var(--warn-line); }
.pills { display: flex; gap: 6px; flex-wrap: wrap; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px;
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; padding: 1px 6px;
  overflow-wrap: anywhere; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.actions form { margin: 0; }
.cred-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 640px) { .cred-grid { grid-template-columns: 1fr; } }
.rider-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 640px) { .rider-grid { grid-template-columns: 1fr 1fr; } }
"""

ICONS = {
    'bolt': '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    'list': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    'target': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    'type': '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41'
           'M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
    'sliders': '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'alert': '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    'lock': '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    'chevron': '<path d="m6 9 6 6 6-6"/>',
    'up': '<path d="m18 15-6-6-6 6"/>',
    'grip': '<path d="M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01"/>',
    'board': '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01'
             'M6 13h.01M10 13h.01M14 13h.01M18 13h.01"/>',
    'phone': '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    'key': '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    'refresh': '<path d="M21 12a9 9 0 1 1-2.64-6.36L21 8M21 3v5h-5"/>',
    'wifi': '<path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"/>',
}

SECTIONS = (  # id, nav title, icon
    ('logins', 'Logins', 'key'), ('rotation', 'Rotation', 'list'), ('timing', 'Timing', 'clock'), ('goals', 'Goals', 'target'),
    ('display', 'Name and text', 'type'), ('schedules', 'Schedules', 'sun'), ('panel', 'Panel', 'board'),
    ('advanced', 'Advanced', 'sliders'),
)

SCRIPT = """
const form = document.getElementById('settings');
const status = document.getElementById('save-status');
const changed = () => {
  form.dataset.dirty = '1';
  status.classList.add('dirty');
  status.querySelector('span:last-child').textContent = 'Unsaved changes';
};
form.addEventListener('input', changed);
form.addEventListener('submit', () => {
  form.dataset.submitting = '1';
  const button = document.getElementById('save');
  button.disabled = true;
  button.querySelector('span').textContent = 'Saving\\u2026';
});
window.addEventListener('beforeunload', e => {
  if (form.dataset.dirty && !form.dataset.submitting) e.preventDefault();
});
document.querySelectorAll('.js-only').forEach(el => { el.hidden = false; });
// Rotation: the switched-on screens are numbered, in order, at the top; one switched off drops
// to the bottom, and one switched on goes to the end of the numbered ones. Each one moves by its
// grip (dragged, or arrow keys) or one place earlier by its arrow.
const screens = document.getElementById('screens');
screens.classList.add('js');
const onRows = () => [...screens.querySelectorAll('.screen-row.on')];
const lastOn = except => onRows().filter(r => r !== except).pop();
screens.addEventListener('change', e => {
  if (!e.target.matches('.switch')) return;
  const row = e.target.closest('.screen-row');
  row.classList.toggle('on', e.target.checked);
  if (e.target.checked) { const last = lastOn(row); last ? last.after(row) : screens.prepend(row); }
  else screens.append(row);
});
function moveBy(row, step) {  // one place among the switched-on screens
  const on = onRows(), i = on.indexOf(row), other = on[i + step];
  if (!other) return;
  step < 0 ? other.before(row) : other.after(row);
  changed();
}
screens.addEventListener('click', e => {
  const move = e.target.closest('.move');
  if (!move) return;
  moveBy(move.closest('.screen-row'), -1);
  move.focus();
});
screens.addEventListener('keydown', e => {
  const grip = e.target.closest('.grip');
  if (!grip || !['ArrowUp', 'ArrowDown'].includes(e.key)) return;
  e.preventDefault();
  moveBy(grip.closest('.screen-row'), e.key === 'ArrowUp' ? -1 : 1);
  grip.focus();
});
let dragged = null;
screens.addEventListener('pointerdown', e => {
  const grip = e.target.closest('.grip');
  if (!grip || e.button > 0 || !grip.closest('.screen-row.on')) return;
  e.preventDefault();
  dragged = grip.closest('.screen-row');
  dragged.classList.add('dragging');
  document.body.classList.add('dragging');
  grip.setPointerCapture(e.pointerId);
});
screens.addEventListener('pointermove', e => {
  if (!dragged) return;
  // It goes before the first other switched-on screen whose middle is below the pointer, else last of them.
  const others = onRows().filter(r => r !== dragged);
  const next = others.find(r => { const box = r.getBoundingClientRect(); return e.clientY < box.top + box.height / 2; });
  if (next) { if (dragged.nextElementSibling !== next) { next.before(dragged); changed(); } }
  else if (others.length && others[others.length - 1].nextElementSibling !== dragged) { others[others.length - 1].after(dragged); changed(); }
});
const drop = () => {
  if (!dragged) return;
  dragged.classList.remove('dragging');
  document.body.classList.remove('dragging');
  dragged = null;
};
screens.addEventListener('pointerup', drop);
screens.addEventListener('pointercancel', drop);
for (const id of ['brightness_schedule', 'refresh_schedule']) {
  const on = document.getElementById(id);
  const show = () => { document.getElementById(id + '-fields').hidden = !on.checked; };
  on.addEventListener('change', show);
  show();
}
const links = [...document.querySelectorAll('.toc a')];
const spy = new IntersectionObserver(entries => entries.forEach(e => {
  if (e.isIntersecting) links.forEach(a => a.classList.toggle('on', a.hash === '#' + e.target.id));
}), {rootMargin: '-80px 0px -65% 0px'});
document.querySelectorAll('main .card[id]').forEach(s => spy.observe(s));
"""


def icon(name):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def document(title, body, script=''):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{escape(title)}</title><style>{STYLE}</style></head>'
            f'<body>{body}{f"<script>{script}</script>" if script else ""}</body></html>')


def _topbar(board=None, mode=None, sign_out=False):
    """mode: ("warn" or "good", text) for the badge on the right. sign_out: a Sign out button after it."""
    chips = f'<span class="chip board">{icon("board")}{escape(board)}</span>' if board else ''
    if mode:
        kind, text = mode
        chips += f'<span class="chip {kind}">{icon("wifi" if kind == "warn" else "lock")}{escape(text)}</span>'
    if sign_out:
        chips += '<form method="post" action="/signout"><button type="submit" class="ghost">Sign out</button></form>'
    return (f'<header class="topbar"><div class="topbar-in"><div class="brand"><span class="mark">{icon("bolt")}</span>'
            f'<div><div class="brand-name">Peloton LED</div><div class="brand-sub">Board settings</div>'
            f'</div></div><div class="top-meta">{chips}</div></div></header>')


def message_page(title, text):
    """A plain page for errors (not found, not allowed)."""
    body = (f'{_topbar()}<div class="center"><div class="card auth"><div class="auth-icon">{icon("info")}</div>'
            f'<h1>{escape(title)}</h1><p>{escape(text)}</p><a class="btn secondary" href="/">Go to settings</a></div></div>')
    return document(title, body)


def _notice(kind, html, role='status'):
    glyph = {'good': 'check', 'bad': 'alert', 'warn': 'info', 'info': 'info'}[kind]
    return f'<div class="notice {kind}" role="{role}">{icon(glyph)}<div>{html}</div></div>'


def notices(problems=(), saved=None):
    """saved: None (nothing saved), or one of SAVED."""
    html = ''
    if problems:
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        html += _notice('bad', f'<strong>Not saved.</strong> Fix these and save again:<ul>{items}</ul>', 'alert')
    if saved == 'restarted':
        html += _notice('good', '<strong>Saved.</strong> The display is restarting with the new settings.')
    elif saved == 'not_running':
        html += _notice('good', "<strong>Saved.</strong> The display isn't running; it uses these settings "
                                'the next time it starts.')
    elif saved == 'saved':
        html += _notice('good', '<strong>Saved.</strong> Restart the display for the new settings.')
    elif saved == 'failed':
        html += _notice('bad', "<strong>Saved, but the display didn't restart.</strong> Run "
                               '<code>sudo systemctl restart peloton-led</code> on the board, or unplug it and '
                               'plug it back in.', 'alert')
    return html


def _attr(value):
    return escape(str(value), quote=True)


def _hint(text):
    return f'<p class="hint">{escape(text)}</p>' if text else ''


def _field(name, label, control, hint='', inline=False):
    """A labelled row: label and hint on the left, the control on the right (stacked on a phone)."""
    return (f'<div class="field{" inline" if inline else ""}"><div class="field-label"><div class="label-row">'
            f'<label for="{name}">{escape(label)}</label></div>{_hint(hint)}</div>'
            f'<div class="field-control">{control}</div></div>')


def _input(name, value='', kind='text', extra=''):
    return f'<input type="{kind}" id="{name}" name="{name}" value="{_attr(value)}"{extra}>'


def _unit(control, unit):
    """A field with its unit ("s", "%") inside its right edge; the label still says what it is."""
    if not unit:
        return control
    return (f'<span class="unit" style="--u: {len(unit)}">{control}'
            f'<span class="unit-text" aria-hidden="true">{escape(unit)}</span></span>')


def _number(name, value, placeholder='', extra='', unit=None):
    """A number field: decimals allowed (step any) unless extra says otherwise."""
    return _unit(_input(name, number_text(value), 'number',
                        f' inputmode="decimal" step="any" min="0" placeholder="{_attr(number_text(placeholder))}"'
                        f'{extra}'), unit)


def _options(name, options, chosen, extra=''):
    """options: (value, text) pairs."""
    opts = ''.join(f'<option value="{_attr(v)}"{" selected" if v == chosen else ""}>{escape(t)}</option>'
                   for v, t in options)
    return f'<select id="{name}" name="{name}"{extra}>{opts}</select>'


def _switch_input(name, on, extra=''):
    return (f'<input type="checkbox" class="switch" role="switch" id="{name}" name="{name}"'
            f'{" checked" if on else ""}{extra}>')


def _switch(name, label, on, hint=''):
    return _field(name, label, _switch_input(name, on), hint, inline=True)


def _section(sid, title, description, body, glyph):
    return (f'<section class="card" id="{sid}" aria-labelledby="{sid}-title"><div class="card-head">'
            f'<span class="card-icon">{icon(glyph)}</span><div><h2 id="{sid}-title">{escape(title)}</h2>'
            f'<p>{escape(description)}</p></div></div><div class="card-body">{body}</div></section>')


def _mini(name, label, control):
    return f'<div><label class="mini" for="{name}">{escape(label)}</label>{control}</div>'


def _screen_row(name, label, hint, on, display):
    """One rotation screen: posted as "rotation_order" in page order, with its switch and time."""
    durations = section(display, 'screen_durations')
    if name in SHARED_DURATION:
        other = dict((n, l) for n, l, _ in SCREENS)[SHARED_DURATION[name]]
        time = f'<span class="time shared">As {escape(other)}</span>'
    else:
        seconds = _number(f'duration_{name}', durations.get(name), duration_fallback(display, name),
                          f' aria-label="{_attr(label)} seconds"', 's')
        time = f'<span class="time">{seconds}</span>'
    switch = _switch_input(f'rotation_on_{name}', on, f' aria-label="Show {_attr(label)}"')
    grip = (f'<button type="button" class="grip js-only" hidden aria-label="Drag to reorder {_attr(label)}, '
            f'or use the arrow keys">{icon("grip")}</button>')
    return (f'<li class="screen-row{" on" if on else ""}"><input type="hidden" name="rotation_order" value="{name}">'
            f'{grip}'
            f'<div><label class="screen-name" for="rotation_on_{name}">{escape(label)}</label>{_hint(hint)}</div>'
            f'{time}{switch}'
            f'<button type="button" class="move js-only" hidden aria-label="Move {_attr(label)} earlier">'
            f'{icon("up")}</button></li>')


def _schedule_switch(sid, label, schedule, hint, fields):
    return (_switch(sid, label, schedule is not None, hint)
            + f'<div class="schedule-wrap" id="{sid}-fields">'
            + ('' if schedule else '<p class="hint schedule-note">Not set up yet: these are suggested starting '
                                   'values, saved only if you turn this on.</p>')
            + fields + '</div>')


# Units for matrix settings that have one.
MATRIX_UNITS = {'brightness': '%', 'pwm_lsb_nanoseconds': 'ns', 'limit_refresh': 'Hz'}


def _matrix_field(key, label, hint, value):
    """A config.json "matrix" setting's row; blank, it's the app's default (MATRIX_DEFAULTS)."""
    name = f'matrix_{key}'
    default = MATRIX_DEFAULTS[key]
    blank = f'Default: {"On" if default is True else "Off" if default is False else default}' \
        if default not in (None, '') else 'Default'
    if key == 'pixel_mapper':
        choices = list(ROTATIONS) + ([(value, value)] if value and value not in dict(ROTATIONS) else [])
        control = _options(name, [('', 'Right way up')] + choices, value or '')
    elif key == 'gpio_mapping':
        # Pi boards need one (the installer stops without it), so "not set" is offered only when it isn't.
        choices = [(m, m) for m in GPIO_MAPPINGS]
        control = _options(name, ([('', 'Not set')] if value not in GPIO_MAPPINGS else []) + choices, value or '')
    elif key in SWITCH_KEYS:
        chosen = '' if value is None else ('true' if value else 'false')
        control = _options(name, [('', blank), ('true', 'On'), ('false', 'Off')], chosen)
    elif isinstance(default, str):
        control = _input(name, value or '', extra=f' class="mono" placeholder="{_attr(blank)}"')
    else:
        control = _unit(_input(name, number_text(value), 'number',
                               f' inputmode="numeric" step="1" placeholder="{_attr(blank)}"'), MATRIX_UNITS.get(key))
    return _field(name, label, control, hint)


def _rider(index, rider, display):
    goals = section(rider, 'weekly_goals')
    shared = section(display, 'weekly_goals')
    name = rider['name']
    fields = (
        _mini(f'rider_{index}_username', 'Name on the board',
              _input(f'rider_{index}_username', rider.get('username') or '',
                     extra=' placeholder="Their Peloton username"'))
        + _mini(f'rider_{index}_workouts', 'Workouts a week',
                _number(f'rider_{index}_workouts', goals.get('workouts'), shared.get('workouts', 0),
                        ' step="1" inputmode="numeric"', 'workouts'))
        + _mini(f'rider_{index}_minutes', 'Minutes a week',
                _number(f'rider_{index}_minutes', goals.get('minutes'), shared.get('minutes', 0),
                        ' step="1" inputmode="numeric"', 'min'))
        + _mini(f'rider_{index}_milestones', 'Milestones',
                _input(f'rider_{index}_milestones', milestones_text(rider.get('milestones')),
                       extra=f' placeholder="{_attr(milestones_text(display.get("milestones")) or "None")}"')))
    return (f'<div class="rider"><h3>{escape(name)}</h3>'
            f'<input type="hidden" name="rider_{index}_name" value="{_attr(name)}">'
            f'<div class="rider-grid">{fields}</div></div>')


MODE_TEXT = {
    'browser': 'This board renews logins by itself: with each rider\'s refresh token, and if Peloton turns '
               'that down, with one browser login a day using the email and password saved here.',
    'no-browser': 'This board renews logins with refresh tokens only (no browser here). If a rider\'s login '
                  'stops working, seed the board again from your computer; passwords saved here aren\'t used.',
    'none': 'Automatic renewal is off on this board (installed with --no-auto-token). Renew now still works.',
}


def _zone(display):
    """The board's zone for times on the page, or the server's own."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(display['timezone']) if isinstance(display.get('timezone'), str) else None
    except (ValueError, KeyError, OSError):
        return None


def _pill(kind, text):
    return f'<span class="pill {kind}">{escape(text)}</span>'


def _token_pill(login, zone):
    token = login.token
    if not token.get('ok'):
        return _pill('bad', 'No working token')
    if token.get('expired'):
        return _pill('bad', f'Expired {when(token["expires_at"], zone)}')
    return _pill('ok', f'Valid until {when(token["expires_at"], zone)}')


def _login_status(login, view, zone):
    pills = [_token_pill(login, zone)]
    if login.padlock:
        pills.append(_pill('warn', 'Padlock on'))
    pills.append(_pill('ok' if login.email_set and login.password_set else '',
                       'Email and password set' if login.email_set and login.password_set
                       else f'Email {"set" if login.email_set else "not set"}, '
                            f'password {"set" if login.password_set else "not set"}'))
    lines = []
    if not login.token.get('ok'):
        lines.append(f'{login.token.get("reason", "unreadable")}.'.capitalize())
    lines.append(login.chain.capitalize() + '.' if login.chain else 'No refresh token: renewal needs a login.')
    if login.padlock:
        lines.append(f'Renewal says: {login.padlock["reason"]}')
    if login.browser_attempt:
        lines.append(f'Last browser login try: {when(login.browser_attempt, zone)}.')
    needs_seed = not login.healthy and view.get('mode') != 'browser'
    seed = (f'<p class="hint">To log in again, run this from the Peloton-LED checkout on your computer: '
            f'<code>{escape(view["seed"])}</code></p>' if needs_seed else '')
    return (f'<div class="login"><div class="login-head"><strong>{escape(login.name)}</strong>'
            f'<span class="pills">{"".join(pills)}</span></div>'
            + ''.join(f'<p class="hint">{escape(line)}</p>' for line in lines) + seed + '</div>')


def _secret_input(name, label, kind, is_set, autocomplete='off'):
    """A write-only field: it never holds the saved value, only says whether there is one."""
    placeholder = 'Saved: type to replace' if is_set else 'Not set'
    return _mini(name, label, _input(name, '', kind, f' autocomplete="{autocomplete}" spellcheck="false" '
                                                     f'placeholder="{placeholder}"'))


def logins_card(view, signed_in=True, outcome=None, problems=(), zone=None):
    """Logins: each rider's health, Renew now and the test alert, and the write-only credentials
    form (only with a PIN session: the setup hotspot alone can't change logins). view: Settings.logins()."""
    if not view:
        return ''
    top = ''
    if problems:
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        top += _notice('bad', f'<strong>Logins not saved.</strong><ul>{items}</ul>', 'alert')
    if outcome in LOGIN_OUTCOMES:
        kind, html = LOGIN_OUTCOMES[outcome]
        top += _notice(kind, html, 'alert' if kind == 'bad' else 'status')
    mode = view.get('mode')
    about = [MODE_TEXT.get(mode, 'Renewal mode unknown (an older install): re-run the installer to record it.')]
    if view.get('renewing'):
        about.append('Renewal is running now.')
    elif view.get('last_run'):
        result = 'worked' if view.get('last_result') == 'success' else f'failed ({view.get("last_result")})'
        about.append(f'Last renewal run: {view["last_run"]}, {result}.')
    about.append(f'Next scheduled check: {view["timer_next"]}.' if view.get('timer_next')
                 else 'No check is scheduled right now (a manual board checks only while the display runs).')
    alerts = view.get('alerts') or {}
    if alerts.get('failures'):
        about.append(f'{alerts["failures"]} failed run{"s" if alerts["failures"] != 1 else ""} in a row; last: '
                     f'{alerts.get("last_message") or "no message"}')
    riders = view.get('riders') or []
    actions = (
        '<div class="actions"><form method="post" action="/renew"><button type="submit" class="secondary">'
        f'{icon("refresh")}Renew now</button></form>'
        + ('<form method="post" action="/alert/test"><button type="submit" class="secondary">'
           f'{icon("phone")}Send a test alert</button></form>' if view.get('pushover') else '')
        + '</div>')
    if signed_in:
        rows = ''.join(
            f'<div class="rider"><h3>{escape(r.name)}</h3><input type="hidden" name="cred_{r.key}_name" '
            f'value="{_attr(r.name)}"><div class="cred-grid">'
            + _secret_input(f'cred_{r.key}_email', 'Peloton email', 'email', r.email_set)
            + _secret_input(f'cred_{r.key}_password', 'Peloton password', 'password', r.password_set, 'new-password')
            + '</div></div>' for r in riders)
        pushover_set = view.get('pushover')
        creds = (
            '<form method="post" action="/credentials" id="credentials"><h3>Change logins</h3>'
            '<p class="hint">Saved to the board\'s auth.env and never shown again, here or anywhere: blank keeps '
            'what\'s saved. This page isn\'t encrypted, so only do this on your own network.</p>'
            + rows
            + '<div class="rider"><h3>Pushover alerts</h3><p class="hint">For renewal problems, and sending the '
              'sign-in PIN to your phone. From pushover.net: your user key, and an app\'s token.</p>'
              '<div class="cred-grid">'
            + _secret_input('pushover_app_token', 'App token', 'password', pushover_set)
            + _secret_input('pushover_user_key', 'User key', 'password', pushover_set)
            + '</div>'
            + (_field('pushover_clear', 'Remove the Pushover keys', _switch_input('pushover_clear', False),
                      'No more alerts or PIN by phone.', inline=True) if pushover_set else '')
            + '</div><div class="actions"><button type="submit" class="primary">'
              f'{icon("lock")}Save logins</button></div></form>')
    else:
        creds = _notice('info', 'Changing logins takes the PIN, even in setup mode: '
                                '<a href="/signin">sign in with the PIN</a>.')
    body = (top + ''.join(f'<p class="hint">{escape(line)}</p>' for line in about)
            + ''.join(_login_status(r, view, zone) for r in riders) + actions + creds)
    return _section('logins', 'Logins', "Each rider's Peloton login, and how the board keeps it working.", body,
                    'key')


def settings_page(config, hotspot=None, problems=(), saved=None, board=None, note=None, logins=None,
                  signed_in=True, login_outcome=None, login_problems=()):
    """The settings form, filled from config. hotspot: the Wi-Fi setup hotspot's name when this
    browser is on it (no PIN needed). note: why config.json couldn't be read, if it couldn't.
    logins: Settings.logins() for the Logins card (None leaves it off); signed_in: a PIN session,
    which changing logins needs."""
    display = section(config, 'display')
    matrix = section(config, 'matrix')
    merged = {**DEFAULTS, **display}  # what the app uses where config.json says nothing

    top = (notices(problems, saved)
           + (_notice('warn', f'<strong>Setup mode.</strong> Anyone who joins <strong>{escape(hotspot)}</strong> '
                              'can open this page while the board is in Wi-Fi setup.') if hotspot else '')
           + (_notice('warn', escape(note)) if note else ''))

    rows = ''.join(_screen_row(name, *dict((n, (l, h)) for n, l, h in SCREENS)[name], on, merged)
                   for name, on in rotation_rows(display))
    rotation = _section('rotation', 'Rotation', 'Which screens the board shows, in this order, and for how long.', (
        f'<ol class="screens" id="screens" aria-label="Screens, in order">{rows}</ol>'
        + _notice('info', 'Seconds per page; blank uses the setting it falls back on (shown greyed out), 0 '
                          'skips the screen. A screen with nothing to show yet is skipped either way.')
    ), 'list')

    timing = _section('timing', 'Timing', 'How long pages last, and how often the board checks Peloton.', ''.join(
        _field(key, label, _number(key, display.get(key), DEFAULTS[key], unit='s'), hint)
        for key, label, hint in TIMING
    ), 'clock')

    shared_goals = section(display, 'weekly_goals')
    rider_list = riders(config)
    goals = _section('goals', 'Goals', 'Weekly goals and all-time milestones.', (
        '<h3>Everyone</h3>'
        + _field('goal_workouts', 'Workouts a week',
                 _number('goal_workouts', shared_goals.get('workouts'), 0, ' step="1" inputmode="numeric"', 'workouts'),
                 '0 or blank for no workouts goal.')
        + _field('goal_minutes', 'Minutes a week',
                 _number('goal_minutes', shared_goals.get('minutes'), 0, ' step="1" inputmode="numeric"', 'min'),
                 '0 or blank for no minutes goal.')
        + _field('milestones', 'Milestones',
                 _input('milestones', milestones_text(display.get('milestones')), extra=' placeholder="100, 250, 500"'),
                 'Total workout counts to celebrate, separated by commas.')
        + _field('milestone_step', 'And every',
                 _number('milestone_step', display.get('milestone_step'), DEFAULTS['milestone_step'],
                         ' step="1" inputmode="numeric"', 'workouts'),
                 'Workouts between milestones past the list (100: 100, 200, 300…). 0 for none.')
        + (('<h3>Each rider</h3><p class="hint">Blank uses Everyone\'s. Setting either weekly goal gives the '
            'rider their own pair (the other blank is no goal).</p>'
            + ''.join(_rider(i, rider, display) for i, rider in rider_list)) if rider_list else '')
    ), 'target')

    reminder = display.get('streak_reminder_day', STREAK_REMINDER_DEFAULT)
    text = _section('display', 'Name and text', 'The name screen and how pages are laid out.', (
        _field('username', 'Name on the board', _input('username', display.get('username') or '',
                                                       extra=' placeholder="Your Peloton username"'),
               'Shown when Peloton has no username to give. Riders have their own in Goals.')
        + _field('font', 'Name font', _options('font', [(f, f.capitalize()) for f in FONTS], merged['font']))
        + _field('color', 'Name colour', _options('color', [(c, c.replace('_', ' ').capitalize()) for c in COLORS],
                                                  merged['color']))
        + _switch('compact_workout_pages', 'Compact workout pages (64x32)', merged['compact_workout_pages'],
                  'On a 64x32 panel, each workout in two still pages instead of one changing page.')
        + _field('streak_reminder_day', 'Streak reminder from',
                 _options('streak_reminder_day', [('off', 'Never')] + [(str(i), d) for i, d in enumerate(WEEKDAYS)],
                          'off' if reminder is None else str(reminder)),
                 'From this day, a week with no workout yet shows "keep your streak" instead of the streak.')
    ), 'type')

    bright = display.get('brightness_schedule') if isinstance(display.get('brightness_schedule'), dict) else None
    quiet = display.get('refresh_schedule') if isinstance(display.get('refresh_schedule'), dict) else None
    b, q = bright or {}, quiet or {}
    level = ' min="1" max="100" step="1" inputmode="numeric"'
    zones = ''.join(f'<option value="{_attr(z)}">' for z in sorted(available_timezones()))
    schedules = _section('schedules', 'Schedules', "Dimming at night and checking Peloton less while you sleep.", (
        _field('timezone', 'Time zone', _input('timezone', display.get('timezone') or '',
                                               extra=' list="zones" autocomplete="off" placeholder="Your Peloton '
                                                     'profile\'s"') + f'<datalist id="zones">{zones}</datalist>',
               'For the schedules, the week\'s start and today\'s date. Like America/New_York.')
        + _schedule_switch('brightness_schedule', 'Day and night brightness', bright, 'Dim the panel at night.',
                           '<div class="schedule">'
                           + _mini('bright_day', 'Day brightness', _unit(_input('bright_day', b.get('day', 80), 'number', level), '%'))
                           + _mini('day_start', 'Day starts', _input('day_start', b.get('day_start', '07:00'), 'time'))
                           + _mini('bright_night', 'Night brightness',
                                   _unit(_input('bright_night', b.get('night', 15), 'number', level), '%'))
                           + _mini('night_start', 'Night starts',
                                   _input('night_start', b.get('night_start', '22:00'), 'time'))
                           + '</div>')
        + _schedule_switch('refresh_schedule', 'Quiet hours', quiet,
                           'Check Peloton less often overnight.',
                           '<div class="schedule three">'
                           + _mini('quiet_start', 'From', _input('quiet_start', q.get('quiet_start', '23:00'), 'time'))
                           + _mini('quiet_end', 'Until', _input('quiet_end', q.get('quiet_end', '05:00'), 'time'))
                           + _mini('quiet_interval', 'Check every',
                                   _unit(_input('quiet_interval', q.get('quiet_interval', 3600), 'number',
                                                ' min="1" step="1" inputmode="numeric"'), 's'))
                           + '</div>')
    ), 'sun')

    sizes = list(PANEL_SIZES) + ([panel_size(matrix)] if panel_size(matrix) not in PANEL_SIZES else [])
    panel = _section('panel', 'Panel', "The LED panel's size, brightness and wiring.", (
        _field('panel_size', 'Panel size', _options('panel_size', [(s, s) for s in sizes], panel_size(matrix)),
               'Columns x rows, as on the panel\'s label.')
        + ''.join(_matrix_field(key, label, hint, matrix.get(key)) for key, label, hint in PANEL_FIELDS)
    ), 'board')

    advanced = (
        '<details class="card" id="advanced"><summary class="card-head">'
        f'<span class="card-icon">{icon("sliders")}</span><div><h2>Advanced</h2>'
        '<p>Logging and panel hardware. Most boards never need these.</p></div>'
        f'<span class="chev">{icon("chevron")}</span></summary><div class="card-body">'
        + _switch('debug', 'Debug logging', config.get('debug', False), "More detail in the display's log.")
        + _notice('warn', 'The wrong panel settings can leave the board dark or flickering. Blank leaves each '
                          'one to the default.')
        + ''.join(_matrix_field(key, key.replace('_', ' ').capitalize(), '', matrix.get(key))
                  for key in advanced_keys())
        + '</div></details>')

    toc = ''.join(f'<a href="#{sid}">{icon(glyph)}{escape(title)}</a>' for sid, title, glyph in SECTIONS)
    mode = ('warn', 'Setup mode') if hotspot else ('good', 'Signed in')
    body = (
        _topbar(board, mode, sign_out=not hotspot)  # on the hotspot there's no PIN session to end
        + f'<div class="shell"><nav class="toc" aria-label="Sections">{toc}</nav><main>'
        + '<div class="page-head"><h1>Settings</h1><p>Changes are checked, saved to the board\'s config.json, '
          'and the display restarts to use them. Logins go to the board\'s auth.env and are never shown.</p></div>'
        + top
        + f'<div class="stack" style="margin-bottom:20px">{logins_card(logins, signed_in, login_outcome, login_problems, _zone(display))}</div>'
        + f'<form method="post" action="/save" id="settings"><input type="hidden" name="{FORM_FIELD}" value="1">'
          f'<div class="stack">{rotation}{timing}{goals}{text}{schedules}{panel}{advanced}</div>'
        + '<div class="savebar"><div class="savebar-in"><div class="status" id="save-status"><span class="dot"></span>'
          '<span>Everything here is saved to config.json</span></div>'
          f'<button type="submit" class="primary" id="save">{icon("check")}<span>Save and restart</span></button>'
          '</div></div></form></main></div>')
    return document('Board settings', body, SCRIPT)


def pin_page(shown_s=None, wrong=False, board=None, phone=False, sent=None, signed_out=False, display_running=True):
    """The sign-in page. shown_s: a PIN is on the board for this long. phone: offer to send it by
    Pushover; sent: how that went, one of SENT. signed_out: just signed out. display_running:
    False when the display isn't running, so a PIN can't show on the panel."""
    status = ''
    if signed_out:
        status = _notice('good', 'Signed out. This browser needs a new PIN to change settings.')
    elif wrong:
        status = _notice('bad', "That isn't the PIN on the board. Try again, or ask for a new one.", 'alert')
    elif sent == 'sent':
        status = _notice('good', "The PIN is on its way to your phone. It's on the board too.")
    elif sent == 'wait':
        status = _notice('warn', 'A PIN went out less than a minute ago: check your phone, or try again in a minute.')
    elif sent == 'used':
        status = _notice('bad', 'That PIN is out of tries. Ask for a new one in a couple of minutes.', 'alert')
    elif sent == 'failed':
        status = _notice('bad', "Couldn't send the PIN (the board's log says why).", 'alert')
    elif shown_s:
        status = _notice('good', f'The PIN is on the board for the next {max(1, round(shown_s / 60))} '
                                 f'minute{"s" if shown_s > 90 else ""}.')
    if not display_running:
        status += _notice('warn', "The display isn't running, so the PIN can't show on the panel. "
                                  + ('Send it to your phone instead, or start' if phone else 'Start')
                                  + ' it with <code>sudo systemctl start peloton-led</code>.')
    body = (
        _topbar(board)
        + f'<div class="center"><div class="card auth"><div class="auth-icon">{icon("lock")}</div>'
          '<h1>Sign in to this board</h1><p>To change this board\'s settings, type in the PIN it shows.</p>'
        + status
        + '<div class="step"><span class="step-n">1</span><div class="step-body"><strong>Show a PIN</strong>'
          f'<p>It appears on the LED board for two minutes{" and can go to your phone" if phone else ""}.</p>'
          f'<div class="buttons"><form method="post" action="/pin/show"><button type="submit" class="secondary">'
          f'{icon("board")}Show a PIN on the board</button></form>'
        + (f'<form method="post" action="/pin/send"><button type="submit" class="secondary">{icon("phone")}'
           'Send the PIN to my phone</button></form>' if phone else '')
        + '</div></div></div>'
        + '<div class="step"><span class="step-n">2</span><div class="step-body"><label for="pin"><strong>Type it in'
          '</strong></label><p>You stay signed in on this browser for an hour.</p>'
          '<form method="post" action="/pin"><input type="text" id="pin" name="pin" class="pin" inputmode="numeric" '
          'autocomplete="one-time-code" pattern="[0-9]*" maxlength="8" required autofocus aria-label="PIN">'
          '<button type="submit" class="primary block">Sign in</button></form></div></div>'
        + '</div></div>')
    return document('Sign in · Board settings', body)

