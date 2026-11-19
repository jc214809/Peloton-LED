"""The settings page's stylesheet, inline because a phone on the setup hotspot has no internet."""

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
.mark { width: 36px; height: 36px; border-radius: 9px; overflow: hidden; box-shadow: var(--shadow); flex: none; }
.mark svg { display: block; width: 100%; height: 100%; stroke: none; }
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
@media (max-width: 440px) { .chip.status { display: none; } .top-meta { gap: 6px; } }

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
/* Power menu (top bar): a details dropdown, so it opens without JavaScript */
.power { position: relative; }
.power > summary { list-style: none; display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px;
  border-radius: 9px; border: 1px solid var(--border-strong); background: var(--surface); color: var(--text);
  font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.power > summary::-webkit-details-marker { display: none; }
.power > summary:hover, .power[open] > summary { background: var(--surface-2); }
.power > summary svg { width: 14px; height: 14px; }
.power > summary svg:last-child { width: 12px; height: 12px; margin-left: -2px; }
.power-menu { position: absolute; right: 0; top: 34px; width: 220px; max-width: calc(100vw - 32px);
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 12px; padding: 6px; z-index: 30;
  box-shadow: 0 8px 24px rgba(0,0,0,.18); }
.power-menu .power-head { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-3);
  padding: 6px 10px 2px; }
.power-menu hr { border: 0; border-top: 1px solid var(--border); margin: 6px 4px; }
.topbar .power-menu button { display: flex; width: 100%; justify-content: flex-start; gap: 10px; height: 36px;
  padding: 0 10px; font-size: 14px; font-weight: 500; border-radius: 8px; background: transparent;
  color: var(--text); text-align: left; }
.topbar .power-menu button:hover { background: var(--surface-2); }
.topbar .power-menu button svg { width: 15px; height: 15px; }
.topbar .power-menu button.danger { color: var(--bad); }
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
.screen-row, .screens-head { display: grid; grid-template-columns: 28px minmax(0, 1fr) 7.5em 42px 32px; gap: 8px 14px;
  align-items: center; padding: 12px 0; border-top: 1px solid var(--border); }
.screen-row:first-child { border-top: 0; }
.screen-row::before { content: ""; width: 24px; height: 24px; }
.screen-row.on { counter-increment: screen; }
.screen-row.on::before { content: counter(screen); border-radius: 50%; display: grid; place-items: center;
  background: var(--accent); color: var(--on-accent); font-size: 12px; font-weight: 650; }
.screen-row:not(.on) .screen-name { color: var(--text-3); }
.screen-name { font-weight: 550; }
.screen-row .shared { color: var(--text-3); font-size: 13px; }
.screen-row .shows { color: var(--text-2); }
.move { width: 32px; height: 32px; padding: 0; border-radius: 8px; background: transparent; color: var(--text-3); }
.move:hover { color: var(--accent); background: var(--accent-soft); }
.move svg { width: 16px; height: 16px; }
.screen-row:first-child .move, .screen-row:not(.on) .move, .screen-row:not(.on) .grip { visibility: hidden; }
/* With the script: a grip on the left of each row, dragged by mouse or finger (pointer events). */
.screens.js .screen-row, .screens-head.js { grid-template-columns: 24px 28px minmax(0, 1fr) 7.5em 42px 32px; }
.screens-head { padding: 4px 0 8px; border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 650;
  text-transform: uppercase; letter-spacing: .06em; color: var(--text-3); }
.screens-head > span { display: flex; align-items: center; gap: 4px; }
.screens-head .grip-col { display: none; }
.screens-head.js .grip-col { display: block; }
.tip-wrap { position: relative; display: inline-flex; }
.tip { width: 18px; height: 18px; padding: 0; border-radius: 50%; background: transparent; color: var(--text-3); }
.tip:hover, .tip:focus-visible { color: var(--accent); }
.tip svg { width: 14px; height: 14px; }
.tip-text { display: none; position: absolute; z-index: 5; top: calc(100% + 6px); right: -8px; width: 240px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25); color: var(--text-2); font-size: 13px; font-weight: 400;
  text-transform: none; letter-spacing: 0; line-height: 1.45; }
.tip-wrap:hover .tip-text, .tip:focus + .tip-text { display: block; }
.screens-head > span:nth-child(2) .tip-text { right: auto; left: -8px; }  /* # is on the left */
.grip { order: -1; width: 24px; height: 32px; padding: 0; border-radius: 6px; background: transparent;
  color: var(--text-3); cursor: grab; touch-action: none; }
.grip:hover { color: var(--accent); background: var(--accent-soft); }
.grip svg { width: 16px; height: 16px; }
.screen-row.dragging { background: var(--accent-soft); border-radius: 10px; box-shadow: var(--shadow); }
.screen-row.dragging .grip { cursor: grabbing; }
body.dragging { user-select: none; -webkit-user-select: none; cursor: grabbing; }
@media (max-width: 640px) { .screen-row, .screens-head { grid-template-columns: 24px minmax(0, 1fr) 42px 32px; }
  .screens.js .screen-row, .screens-head.js { grid-template-columns: 24px 24px minmax(0, 1fr) 42px 32px; }
  .screens-head .seconds-col { display: none; }
  .screen-row .time { grid-column: 2 / -1; } .screens.js .screen-row .time { grid-column: 3 / -1; } }

/* Riders */
.rider { padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); margin-top: 12px; }
.rider > .hint { margin: -4px 0 12px; }
.rider h3 { margin: 0 0 10px; text-transform: none; letter-spacing: 0; font-size: 15px; color: var(--text); }
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
.facts { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 10px 20px; margin: 0;
  padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); font-size: 14px; }
.facts dt { color: var(--text-3); font-weight: 600; }
.card-body > .facts { margin-top: 12px; }
.facts dd { margin: 0; display: flex; align-items: center; gap: 6px 8px; flex-wrap: wrap; }
.facts .hint { margin: 0; }
@media (max-width: 640px) { .facts { grid-template-columns: 1fr; gap: 2px; } .facts dd { margin-bottom: 8px; } }
.facts .whole { flex-basis: 100%; }
details.incomplete > summary { cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
details.incomplete ul { margin: 8px 0 0; padding-left: 18px; }
details.incomplete li { margin: 4px 0; }
.pill.now { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
.pill.now::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor;
  animation: beat 1.2s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) { .pill.now::before { animation: none; } }
details.rider-card { border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); margin-top: 12px; }
details.rider-card > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 14px; }
details.rider-card > summary::-webkit-details-marker { display: none; }
details.rider-card > summary strong { font-size: 15px; }
details.rider-card > summary .what { color: var(--text-2); font-size: 14px; flex: 1; }
details.rider-card > summary .chev svg { width: 16px; height: 16px; color: var(--text-3); display: block; transition: transform .15s; }
details.rider-card[open] > summary { border-bottom: 1px solid var(--border); }
details.rider-card[open] > summary .what { visibility: hidden; }
details.rider-card[open] > summary .chev svg { transform: rotate(180deg); }
.rider-body { padding: 12px 14px 14px; }
.rider-body > .hint { margin: 10px 0 0; }
.rider-facts { display: grid; grid-template-columns: 9.5em minmax(0, 1fr); gap: 6px 20px; font-size: 14px; }
.rider-facts .k { color: var(--text-3); font-weight: 600; }
details.cred { grid-column: 1 / -1; margin: 0 -8px; border-radius: 8px; }
details.cred > summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 9.5em minmax(0, 1fr);
  gap: 20px; padding: 4px 8px; border-radius: 8px; }
details.cred > summary::-webkit-details-marker { display: none; }
details.cred > summary:hover { background: var(--accent-soft); }
details.cred > summary .change { color: var(--accent); font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
details.cred > summary .change svg { width: 14px; height: 14px; }
details.cred[open] { background: var(--surface); border: 1px solid var(--border); margin-top: 4px; }
details.cred[open] > summary .change { display: none; }
.cred-edit { padding: 6px 8px 12px; }
.cred-edit .hint { margin: 0 0 8px; }
.cred-edit .actions { margin-top: 12px; }
@media (max-width: 640px) { .rider-facts, details.cred > summary { grid-template-columns: 1fr; gap: 2px; }
  .rider-facts .k:not(:first-child) { margin-top: 6px; } }
.add-row { display: flex; gap: 8px; }
#update-check { margin-top: 12px; }  /* the check's result, under the channel and Check */
.add-row select { flex: 1; min-width: 0; }
.changes { margin: 0 0 12px; }
.changes ul { margin: 6px 0 0; padding-left: 0; list-style: none; display: grid; gap: 4px; font-size: 14px; }
.changes li { display: flex; gap: 8px; }
.changes li a, .changes li .mono { flex: none; min-width: 3.2em; color: var(--text-3); }
.changes ul.notes { display: block; list-style: disc; margin: 4px 0 2px; padding-left: 18px; color: var(--text-2);
  font-size: 13px; }
.changes ul.notes li { display: list-item; margin-top: 2px; }
.notice .changes { margin: 8px 0 0; }
.notice.new { color: var(--text); background: var(--accent-soft); border-color: var(--accent); }
.notice.new svg { color: var(--accent); }
.notice .when { color: var(--text-3); font-weight: 400; }
.steps { list-style: none; margin: 10px 0; padding: 0; display: grid; gap: 6px; }
.steps li { display: flex; align-items: center; gap: 10px; color: var(--text-3); }
.steps li::before { content: ""; flex: none; width: 8px; height: 8px; border-radius: 50%; border: 2px solid currentColor; }
.steps li.done { color: var(--good); }
.steps li.done::before { background: currentColor; }
.steps li.now { color: var(--text); font-weight: 600; }
.steps li.now::before { border-color: var(--accent); background: var(--accent); animation: beat 1.2s ease-in-out infinite; }
.steps li.failed { color: var(--bad); font-weight: 600; }
.steps li.failed::before { background: currentColor; }
@keyframes beat { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .steps li.now::before { animation: none; } }
"""
