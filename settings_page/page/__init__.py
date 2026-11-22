"""The settings page's HTML: the form for config.json (fields named as form.apply_form reads
them), the PIN page, and the notices after a save. Everything is inline (styles, icons, a few
lines of script), since a phone on the Wi-Fi setup hotspot has no internet to fetch anything
from. It works without JavaScript; the script adds dragging and moving screens in the rotation
(a switched-off one drops to the bottom) and the "unsaved changes" state.
No secret is ever put on it: logins and Pushover keys stay in auth.env.
The Updates card (updates.py) checks for, starts and follows updates; its script checks once the
page loads and follows a running update.

One module per card or job (docs/dev/SETTINGS-PAGE.md has the map). This file only re-exports what
server.py and the tests reach for.
"""
from settings_page.page.alerts_section import ALERT_OUTCOMES
from settings_page.page.assemble import settings_page
from settings_page.page.logins_section import LOGIN_OUTCOMES, renewal_status
from settings_page.page.rotation_section import shows_for
from settings_page.page.shell import POWER_OUTCOMES, SAVED, SENT, TOUCH_ICON, message_page, pin_page
from settings_page.page.updates_section import check_result
from settings_page.page.widgets import _zone

__all__ = ['ALERT_OUTCOMES', 'LOGIN_OUTCOMES', 'POWER_OUTCOMES', 'SAVED', 'SENT', 'TOUCH_ICON', 'check_result',
           'message_page', 'pin_page', 'renewal_status', 'settings_page', 'shows_for', '_zone']
