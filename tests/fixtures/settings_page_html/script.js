
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
  button.querySelector('span').textContent = 'Saving\u2026';
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
document.getElementById('screens-head').classList.add('js');
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
// A rider's Email & password row: Cancel clears what was typed and closes it again. (Without the
// script there's no Cancel: clicking the row closes it.)
document.addEventListener('click', e => {
  const cancel = e.target.closest('[data-cancel]');
  if (!cancel) return;
  const panel = cancel.closest('details.cred');
  panel.querySelectorAll('input:not([type=hidden])').forEach(i => { i.value = ''; });
  panel.open = false;
  panel.querySelector('summary').focus();
});
// A renewal that's running: follow it, swapping in the status block until it's done.
const followRenewal = () => setTimeout(async () => {
  try {
    const reply = await fetch('/renew/status', {headers: {Accept: 'application/json'}});
    const now = await reply.json();
    document.getElementById('renewal').outerHTML = now.html;
    if (now.renewing) followRenewal();
  } catch { followRenewal(); }
}, 5000);
if (document.querySelector('#renewal[data-running]')) followRenewal();
// Updates: the buttons say they're working (a check can take a while), Roll back asks first, and
// while an update runs the page follows it, reloading once it's done. The settings page restarts
// during an update, so a failed ask just tries again.
// On the document, not each form: the page's own check puts in an Update now form later.
document.addEventListener('submit', e => {
  const f = e.target;
  if (!f.matches('form[data-busy]')) return;
  if (f.dataset.confirm && !confirm(f.dataset.confirm)) return e.preventDefault();
  const button = f.querySelector('button[type=submit]');
  button.disabled = true;
  button.querySelector('span').textContent = f.dataset.busy;
});
// Power menu: closes on an outside click or Escape (it works without this, as a plain details).
const power = document.querySelector('details.power');
if (power) {
  document.addEventListener('click', e => { if (!power.contains(e.target)) power.open = false; });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && power.open) { power.open = false; power.querySelector('summary').focus(); }
  });
}
const updateRunning = document.getElementById('update-running');
if (updateRunning) {
  const follow = async () => {
    try {
      const reply = await fetch('/update/status', {headers: {Accept: 'application/json'}});
      const now = await reply.json();
      if (!now.running) return location.replace('/?t=' + Date.now() + '#updates');
      document.getElementById('update-phase').textContent = now.phase;
      const steps = document.getElementById('update-steps');
      if (steps) {
        steps.hidden = now.step === null;
        steps.querySelectorAll('li').forEach((li, i) => {
          li.className = i < now.step ? 'done' : i === now.step ? 'now' : '';
          if (i === now.step) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
        });
      }
    } catch {}
    setTimeout(follow, 5000);
  };
  setTimeout(follow, 5000);
}
// No check yet: check the installed channel now (the board keeps it ten minutes), without
// reloading the page over unsaved settings.
const autoCheck = document.querySelector('#update-check[data-auto]');
if (autoCheck) (async () => {
  try {
    const reply = await fetch('/update/check', {method: 'POST', body: new URLSearchParams({channel: autoCheck.dataset.auto}),
                                                headers: {Accept: 'application/json'}});
    autoCheck.outerHTML = (await reply.json()).html;  // a signed-out page gets HTML back, and lands in catch
  } catch {
    autoCheck.querySelector('div').textContent = "Couldn't check: press Check to try again.";
  }
})();
const links = [...document.querySelectorAll('.toc a')];
const spy = new IntersectionObserver(entries => entries.forEach(e => {
  if (e.isIntersecting) links.forEach(a => a.classList.toggle('on', a.hash === '#' + e.target.id));
}), {rootMargin: '-80px 0px -65% 0px'});
document.querySelectorAll('main .card[id]').forEach(s => spy.observe(s));
