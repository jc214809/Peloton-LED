"""The settings pages' form helper (settings_page/page/form_fetch.js), run under Node with a faked browser: a form's submit is
sent with fetch (Safari on iPhone warns about a form posted over plain http, and doesn't about fetch), and what the board
answers is shown the way a plain form post would show it. Also checked: every page with a form carries the helper, the
forms still post themselves without it, and the server still turns away a post from another site."""

import json
import re
import shutil
import subprocess

import pytest

from settings_page import page
from settings_page.page.script import FORM_FETCH, FORM_SCRIPT, SCRIPT
from tests.test_settings_form import TWO_RIDERS, posted
from tests.test_settings_server import Board

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='the helper runs under Node')

# A faked browser. The helper's capture listener is on `document`, its main one on `window`; firing an event runs them in
# the browser's order: document capture, the page's own document-level listeners (`pageListeners`), then window.
PRELUDE = """
const docListeners = [], winListeners = [], pageListeners = [], calls = [];
globalThis.document = {addEventListener: (type, fn, capture) => docListeners.push([type, fn, !!capture]),
                       open: () => calls.push(['open']), write: html => calls.push(['write', html]),
                       close: () => calls.push(['close'])};
globalThis.window = globalThis;
globalThis.addEventListener = (type, fn) => winListeners.push([type, fn]);
globalThis.location = {pathname: '/', search: '', reload: () => calls.push(['reload']),
                       assign: url => calls.push(['assign', url])};
globalThis.history = {replaceState: (a, b, url) => calls.push(['replaceState', url])};
globalThis.alert = text => calls.push(['alert', text]);
globalThis.FormData = function (form) { return form.fields; };
const env = () => ({location, history, document, fetch: globalThis.fetch});
const fire = async (form, submitter) => {
  const e = {target: form, submitter, defaultPrevented: false,
             preventDefault() { this.defaultPrevented = true; calls.push(['preventDefault']); }};
  for (const [type, fn, capture] of docListeners) if (type === 'submit' && capture) fn(e);
  for (const fn of pageListeners) fn(e);
  for (const [type, fn] of winListeners) if (type === 'submit') await fn(e);
};
const makeForm = (action, fields, extra = {}) => ({method: 'post', fields, getAttribute: () => action, closest: () => null,
                                                   dataset: {}, elements: [], ...extra});
"""


def run(body):
    # The block makes the helper's consts local, as on a page; the test body sits inside it, with them.
    script = PRELUDE + '{\n' + FORM_FETCH + '\n(async () => {\n' + body + '\nconsole.log(JSON.stringify(calls));\n})();\n}'
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@needs_node
def test_a_form_is_sent_with_fetch_with_its_fields_the_pressed_button_and_the_session_cookie():
    calls = run("""
        globalThis.fetch = async (url, init) => {
          calls.push(['fetch', url, init.method, init.credentials, String(init.body)]);
          return {redirected: true, url: 'http://board/?x'};
        };
        await fire(makeForm('/pin', [['pin', '1234']]), {name: 'go', value: 'yes'});""")
    assert calls[0] == ['preventDefault']
    assert calls[1] == ['fetch', '/pin', 'POST', 'same-origin', 'pin=1234&go=yes']


@needs_node
def test_a_button_without_a_name_adds_nothing():
    calls = run("""
        globalThis.fetch = async (url, init) => {
          calls.push(['body', String(init.body)]);
          return {redirected: true, url: 'http://board/signin'};
        };
        await fire(makeForm('/power', [['action', 'reboot']]), {name: '', value: ''});""")
    assert ['body', 'action=reboot'] in calls


@needs_node
def test_a_redirect_is_followed_to_the_page_it_names_keeping_the_cards_anchor():
    calls = run("""
        globalThis.fetch = async () => ({redirected: true, url: 'http://board/?update=started'});
        await sendForm('/update/start', new URLSearchParams(), '#updates', env());""")
    assert calls == [['assign', 'http://board/?update=started#updates']]


@needs_node
def test_a_redirect_to_the_page_already_open_reloads_it():
    calls = run("""
        globalThis.fetch = async () => ({redirected: true, url: 'http://board/'});
        await sendForm('/update/check', new URLSearchParams(), '#updates', env());""")
    assert calls == [['replaceState', 'http://board/#updates'], ['reload']]


@needs_node
def test_a_redirect_to_the_sign_in_page_takes_no_anchor():
    calls = run("""
        globalThis.fetch = async () => ({redirected: true, url: 'http://board/signin'});
        await sendForm('/credentials', new URLSearchParams(), '#logins', env());""")
    assert calls == [['assign', 'http://board/signin']]


@needs_node
def test_a_page_answered_without_a_redirect_replaces_the_document():
    calls = run("""
        globalThis.fetch = async () => ({redirected: false, text: async () => '<p>Not saved</p>'});
        await sendForm('/save', new URLSearchParams(), '', env());""")
    assert calls == [['open'], ['write', '<p>Not saved</p>'], ['close']]


@needs_node
def test_a_form_in_a_card_carries_that_cards_anchor():
    calls = run("""
        globalThis.fetch = async () => ({redirected: true, url: 'http://board/?alerts=sent'});
        await fire(makeForm('/alert/test', [], {closest: () => ({id: 'alerts'})}), null);""")
    assert calls[-1] == ['assign', 'http://board/?alerts=sent#alerts']


@needs_node
def test_a_refused_confirm_sends_nothing():
    # The page's own handler (Roll back's confirm) is on the document and has called preventDefault by the time the
    # helper's window listener runs, whichever script registered first.
    calls = run("""
        globalThis.fetch = async () => { calls.push(['fetch']); };
        pageListeners.push(e => e.preventDefault());
        await fire(makeForm('/update/rollback', []), null);""")
    assert calls == [['preventDefault']]


@needs_node
def test_a_get_form_is_left_alone():
    calls = run("""
        globalThis.fetch = async () => { calls.push(['fetch']); };
        await fire(makeForm('/search', [], {method: 'get'}), null);""")
    assert calls == []


@needs_node
def test_a_board_that_cannot_be_reached_puts_the_buttons_back_and_says_so():
    calls = run("""
        globalThis.fetch = async () => { throw new TypeError('offline'); };
        const button = {type: 'submit', disabled: false, innerHTML: '<span>Save</span>'};
        const form = makeForm('/save', [], {dataset: {submitting: '1'}, elements: [button, {type: 'text'}]});
        const e = {target: form, defaultPrevented: false, preventDefault() {}};
        for (const [t, fn, capture] of docListeners) if (t === 'submit' && capture) fn(e);
        button.disabled = true; button.innerHTML = '<span>Saving</span>';  // what the page's own handler does
        for (const [t, fn] of winListeners) if (t === 'submit') await fn(e);
        calls.push(['button', button.disabled, button.innerHTML, form.dataset.submitting]);""")
    assert calls[0][0] == 'alert' and "didn't reach the board" in calls[0][1]
    assert calls[1] == ['button', False, '<span>Save</span>', None]


@needs_node
def test_a_server_that_answers_with_an_error_status_still_shows_its_page():
    calls = run("""
        globalThis.fetch = async () => ({redirected: false, status: 403, text: async () => '<h1>Not allowed</h1>'});
        await fire(makeForm('/save', []), null);""")
    assert ['write', '<h1>Not allowed</h1>'] in calls


@needs_node
def test_the_real_scripts_are_valid_javascript():
    for name, script in (('main', SCRIPT), ('sign-in', FORM_SCRIPT)):
        out = subprocess.run([NODE, '--check', '-'], input=script, capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, f'{name}: {out.stderr}'


def test_the_main_and_sign_in_pages_carry_the_helper_in_a_block():
    assert FORM_FETCH in SCRIPT and SCRIPT.startswith('{\n') and SCRIPT.rstrip().endswith('}')
    assert FORM_SCRIPT == '{\n' + FORM_FETCH + '}\n'
    assert FORM_SCRIPT in page.pin_page(board='b')
    assert SCRIPT in page.settings_page(TWO_RIDERS)


def test_a_replaced_pages_polls_stop():
    """A page the board answers with is written over this one, and timers outlive that: the renewal and update polls
    would go on every 5 s (the renewal's failing on the missing #renewal) beside the new page's own."""
    for poll in ('const followRenewal = () => setTimeout(async () => {', 'const follow = async () => {'):
        assert poll + '\n' in SCRIPT
        assert SCRIPT.split(poll + '\n', 1)[1].lstrip().startswith('if (!form.isConnected) return;'), poll


def test_no_script_makes_its_own_form_or_submits_one():
    # A script-made form would get Safari's prompt too, and the helper only sees the submit events the browser fires.
    for script in (SCRIPT, FORM_SCRIPT):
        assert "createElement('form')" not in script and '.submit()' not in script


def test_every_form_still_posts_itself_without_the_script():
    html = page.pin_page(board='b', phone=True)
    assert re.findall(r'<form method="post" action="(/[a-z/]+)"', html) == ['/pin/show', '/pin/send', '/pin']


@pytest.fixture
def board(tmp_path, monkeypatch):
    b = Board(tmp_path, monkeypatch)
    yield b
    b.httpd.shutdown()
    b.httpd.server_close()


def test_every_form_on_the_main_page_is_a_plain_post_form(board):
    board.sign_in()
    html = board.request('/')[2].split('<script>')[0]  # the markup: the script's comments name forms too
    forms = html.count('<form ')
    assert forms >= 4  # Save, Sign out, the Power menu's, the Logins and Pushover cards'
    assert len(re.findall(r'<form method="post" action="/[a-z/]+"', html)) == forms


def test_the_pages_own_origin_is_accepted_and_another_sites_is_refused_for_every_post(board):
    board.sign_in()
    own = {'Origin': board.url}
    for path in ('/save', '/credentials', '/renew', '/alert/test', '/power', '/signout'):
        assert board.request(path, {'action': 'x'}, own)[0] != 403, path  # fetch sends the page's Origin
    board.sign_in()
    for path in ('/save', '/credentials', '/renew', '/alert/test', '/power', '/signout', '/pin', '/pin/show', '/pin/send'):
        for origin in ('http://evil.example', 'null', board.url.replace('127.0.0.1', 'localhost')):
            status, _, _ = board.request(path, posted(TWO_RIDERS, debug='on'), {'Origin': origin})
            assert status == 403, (path, origin)
    assert board.saved() == TWO_RIDERS and board.restarts == []
