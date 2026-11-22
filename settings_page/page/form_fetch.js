// Every button on the settings pages is a <form method="post"> submit. Safari on iPhone warns "this form is not secure,
// Send Anyway" for any form posted over plain http, and doesn't for fetch(), so with this script each POST form is sent
// with fetch() instead: same URL, same fields plus the pressed button's name, same-origin cookies. Without the script
// the forms post themselves as before. Document-level listeners, so a form the page adds later is covered too.
// It sits in a block on each page (a page the board answers with is written over this one by document.write, and its
// script runs in the same scope: a block keeps the consts from being declared twice).
// Showing what the board answered: a redirect (every save, sign-in and sign-out) is followed to the page it names, as
// the browser would; a page (a problem, a refused save, a Power message) replaces this one.
const showReply = async (reply, hash, env = window) => {
  const where = env.location;
  if (reply.redirected) {
    const to = new URL(reply.url);  // fetch drops the redirect's #fragment: the form's card says where it lands
    if (to.pathname === '/') to.hash = hash;
    if (to.pathname + to.search === where.pathname + where.search) {  // the same page again: assign() wouldn't reload it
      env.history.replaceState(null, '', to.href);
      where.reload();
    } else {
      where.assign(to.href);
    }
    return;
  }
  const html = await reply.text();
  env.document.open();
  env.document.write(html);
  env.document.close();
};
const sendForm = async (url, params, hash = '', env = window) => {
  const reply = await env.fetch(url, {method: 'POST', body: params, credentials: 'same-origin'});
  await showReply(reply, hash, env);
};
// The form's fields as the browser would post them, with the button that was pressed (if it has a name).
const fieldsOf = (form, submitter) => {
  const params = new URLSearchParams(new FormData(form));
  if (submitter && submitter.name) params.append(submitter.name, submitter.value);
  return params;
};
const buttonsOf = form => [...(form.elements || [])].filter(el => el.type === 'submit');
// Capture phase, so it sees the buttons before the page's own handlers say "Saving..." on them.
document.addEventListener('submit', e => {
  const form = e.target;
  form.pelotonButtons = buttonsOf(form).map(b => [b, b.disabled, b.innerHTML]);
}, true);
// On the window, so it runs after every handler on the form and the document: one that refused (Roll back's confirm)
// has called preventDefault by then, and nothing is sent.
window.addEventListener('submit', async e => {
  const form = e.target;
  if (e.defaultPrevented || !window.fetch || (form.method || '').toLowerCase() !== 'post') return;
  e.preventDefault();
  const card = form.closest ? form.closest('section.card[id]') : null;
  try {
    await sendForm(form.getAttribute('action') || location.pathname, fieldsOf(form, e.submitter), card ? '#' + card.id : '');
  } catch (error) {  // the board couldn't be reached: put the buttons back, so the person can press again
    delete form.dataset.submitting;
    (form.pelotonButtons || []).forEach(([button, disabled, html]) => { button.disabled = disabled; button.innerHTML = html; });
    alert("That didn't reach the board: check the connection and try again.");
  }
});
