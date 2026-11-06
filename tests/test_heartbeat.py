"""The display's heartbeat, which the updater's health check reads (self_update)."""
import json
import os

from utils import heartbeat


def test_a_beat_says_when_and_which_process(tmp_path):
    path = tmp_path / 'health'
    assert heartbeat.beat(path=str(path), clock=lambda: 1234.5)
    assert json.loads(path.read_text()) == {'at': 1234.5, 'pid': os.getpid()}
    assert heartbeat.read(str(path)) == {'at': 1234.5, 'pid': os.getpid()}
    assert not list(tmp_path.glob('*.new')), 'written whole, by rename'


def test_without_its_folder_nothing_is_written_or_logged(tmp_path, caplog):
    # A dev machine or the emulator: no peloton-led.service RuntimeDirectory.
    assert heartbeat.beat() is False  # conftest's HEARTBEAT_FILE: a folder that isn't there
    assert not os.path.exists(heartbeat.HEARTBEAT_FILE) and 'heartbeat' not in caplog.text


def test_a_heartbeat_that_cant_be_written_is_warned_about_once(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(heartbeat.logger, 'warning', warnings.append)
    blocked = tmp_path / 'health'
    blocked.mkdir()  # a folder where the file goes: os.replace fails
    assert heartbeat.beat(path=str(blocked)) is False
    assert heartbeat.beat(path=str(blocked)) is False
    assert len(warnings) == 1 and "Can't write the heartbeat" in warnings[0]
    os.rmdir(blocked)
    assert heartbeat.beat(path=str(blocked)) is True
    blocked.unlink()
    blocked.mkdir()
    assert heartbeat.beat(path=str(blocked)) is False and len(warnings) == 2, 'a new failure is said again'


def test_reading_a_missing_or_bad_heartbeat_gives_none(tmp_path):
    path = tmp_path / 'health'
    assert heartbeat.read(str(path)) is None
    for text in ('not json', '[1]', '{"at": "now"}', '{"pid": 3}'):
        path.write_text(text)
        assert heartbeat.read(str(path)) is None, text


def test_the_display_beats_after_each_screen(monkeypatch):
    import peloton_led
    beats = []
    monkeypatch.setattr(peloton_led.heartbeat, 'beat', lambda: beats.append(True))
    monkeypatch.setattr(peloton_led, 'shown_pin', lambda: None)

    class Manager:
        matrix = current = None

        def show(self, name, state):
            assert not beats, 'after the screen, not before'

        def tick(self, state):
            pass

    peloton_led.show_and_wait(Manager(), 'username', {}, 0)
    assert beats == [True]
