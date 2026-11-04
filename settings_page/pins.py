"""The settings page's PIN: asking for one puts a 4-digit PIN on the LED board (the display reads
PIN_FILE; display/ui/settings_pin.py) for PIN_SHOWN_S, and typing it in gives that browser a
session for SESSION_S. A PIN takes TRIES_PER_PIN guesses, and a new one comes only once the last
has run out, so guessing is slow and lights up the board. With Pushover keys (auth.env), the PIN
can also be sent to a phone, at most once every SEND_EVERY_S, since anyone on the Wi-Fi can press
the button. Nothing is saved: a restart of the server signs everyone out.
"""
import logging
import os
import secrets
import threading
import time

logger = logging.getLogger('peloton-led.settings')

# /run is cleared at boot, so a PIN never outlives the server. peloton-settings.service makes the
# folder (RuntimeDirectory, group peloton-led) so the display, once it drops root, can read it.
PIN_FILE = os.environ.get('PELOTON_SETTINGS_PIN_FILE') or '/run/peloton-led-settings/pin'
PIN_DIGITS = 4
PIN_SHOWN_S = 120
SESSION_S = 60 * 60
TRIES_PER_PIN = 5
MAX_SESSIONS = 20  # a few phones and laptops; the oldest goes first
SEND_EVERY_S = 60


class PinGate:
    def __init__(self, pin_file=PIN_FILE, clock=time.time):
        self.pin_file, self.clock = pin_file, clock
        self._lock = threading.Lock()
        self._pin, self._expires, self._tries = None, 0.0, 0
        self._last_send = None
        self._sessions = {}  # token: when it runs out

    def show_pin(self):
        """Put a PIN on the board, or keep the one that's up (or used up) until it runs out.
        Returns its seconds left."""
        with self._lock:
            return self._show(self.clock())

    def send_pin(self, send):
        """Put a PIN on the board as show_pin does, and send it to a phone with send(pin, seconds
        left), which returns whether it went. "sent"; "wait" (one went less than SEND_EVERY_S
        ago); "used" (the PIN is out of tries until it runs out); or "failed" (logged, without
        the PIN)."""
        with self._lock:
            now = self.clock()
            if self._last_send is not None and now - self._last_send < SEND_EVERY_S:
                return 'wait'
            self._last_send = now  # failed sends count too, so the button can't hammer Pushover
            left = self._show(now)
            if self._tries >= TRIES_PER_PIN:
                return 'used'
            pin = self._pin
        try:  # outside the lock: a slow network mustn't hold up typing a PIN in
            sent = send(pin, left)
        except Exception as exc:  # anything the sender didn't catch: say so on the page
            logger.error("Settings page: couldn't send the PIN by Pushover (%s: %s).", type(exc).__name__, exc)
            return 'failed'
        if not sent:
            return 'failed'
        logger.info('Settings page: sent the PIN by Pushover.')
        return 'sent'

    def _show(self, now):
        """A new PIN on the board once the last has run out or been used to sign in."""
        if now >= self._expires or self._pin is None:
            self._pin = ''.join(secrets.choice('0123456789') for _ in range(PIN_DIGITS))
            self._expires, self._tries = now + PIN_SHOWN_S, 0
            self._write(f'{self._pin} {self._expires:.0f}\n')
            logger.info('Settings page: a PIN is on the board.')
        return self._expires - now

    def try_pin(self, pin):
        """A session token for the right PIN while it's up, else None."""
        with self._lock:
            now = self.clock()
            if self._pin is None or now >= self._expires or self._tries >= TRIES_PER_PIN:
                return None
            if not secrets.compare_digest(str(pin).strip(), self._pin):
                self._tries += 1
                logger.warning('Settings page: wrong PIN (%d of %d tries).', self._tries, TRIES_PER_PIN)
                if self._tries >= TRIES_PER_PIN:
                    self._remove()  # off the board; no new one until this one's time is up
                return None
            self._pin = None
            self._remove()
            token = secrets.token_urlsafe(24)
            self._sessions = {t: end for t, end in self._sessions.items() if end > now}
            while len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(min(self._sessions, key=self._sessions.get))
            self._sessions[token] = now + SESSION_S
            logger.info('Settings page: signed in with the PIN.')
            return token

    def sign_out(self, token):
        """End this browser's session, if it has one."""
        with self._lock:
            if self._sessions.pop(token, None) is not None:
                logger.info('Settings page: signed out.')

    def signed_in(self, token):
        with self._lock:
            return bool(token) and self._sessions.get(token, 0) > self.clock()

    def _write(self, text):
        temp = self.pin_file + '.new'
        try:
            # 0640: the display reads it as group peloton-led after dropping root.
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(temp, self.pin_file)
        except OSError as exc:
            logger.error("Settings page: can't put the PIN on the board (%s): %s", self.pin_file, exc)

    def _remove(self):
        try:
            os.remove(self.pin_file)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.error("Settings page: can't take the PIN off the board (%s): %s", self.pin_file, exc)
