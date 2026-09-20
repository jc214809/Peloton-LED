import unittest
from unittest.mock import Mock

import requests

from display.ui.manager import ScreenManager
from peloton.api import PelotonClient


def response(status):
    result = requests.Response()
    result.status_code = status
    result._content = b'{}'
    return result


class LoginIndicatorTests(unittest.TestCase):
    def test_rejected_token_survives_server_failure_and_clears_on_success(self):
        session = Mock()
        session.get.side_effect = [response(401), response(503), response(200)]
        client = PelotonClient(session)
        for expected in (True, True, False):
            try:
                client.get_perf_graph("workout")
            except requests.HTTPError:
                pass
            self.assertEqual(client.login_required, expected)

    def test_network_failure_does_not_request_login(self):
        session = Mock()
        session.get.side_effect = requests.ConnectionError("offline")
        client = PelotonClient(session)
        with self.assertRaises(requests.ConnectionError):
            client.get_me()
        self.assertFalse(client.login_required)

    def test_all_endpoints_record_unauthorized_responses(self):
        for method, args in (("get_me", ()), ("get_overview", ("user",)),
                             ("get_workouts_page", ("user", 50)),
                             ("get_perf_graph", ("workout",))):
            with self.subTest(method=method):
                session = Mock()
                session.get.return_value = response(401)
                client = PelotonClient(session)
                try:
                    getattr(client, method)(*args)
                except requests.HTTPError:
                    pass
                self.assertTrue(client.login_required)

    def test_overlay_follows_auth_status_on_both_panel_sizes(self):
        for height in (32, 64):
            with self.subTest(height=height):
                matrix = Mock(width=64, height=height)
                screen = Mock()
                required = Mock(return_value=True)
                manager = ScreenManager(matrix, initial=screen, login_required=required)
                state = {"calories": 200}
                manager.tick(state)
                self.assertNotIn("login_required", state)
                self.assertTrue(screen.render.call_args.args[1]["login_required"])
                lit = [c.args for c in matrix.SetPixel.call_args_list if c.args[2:] == (255, 160, 0)]
                self.assertTrue(lit)
                self.assertTrue(all(57 <= x < 64 and height - 9 <= y < height for x, y, *_ in lit))
                matrix.SetPixel.reset_mock()
                required.return_value = False
                manager.tick(state)
                matrix.SetPixel.assert_not_called()
                self.assertFalse(screen.render.call_args.args[1]["login_required"])

    def test_stale_clock_uses_bottom_left_and_can_coexist_with_login(self):
        for height in (32, 64):
            with self.subTest(height=height):
                matrix = Mock(width=64, height=height)
                screen = Mock()
                manager = ScreenManager(matrix, initial=screen,
                    login_required=lambda: True, stale_data=lambda: True)
                state = {"calories": 200}
                manager.tick(state)
                rendered = screen.render.call_args.args[1]
                self.assertTrue(rendered['login_required'])
                self.assertTrue(rendered['data_stale'])
                blue = [c.args for c in matrix.SetPixel.call_args_list
                        if c.args[2:] == (70, 170, 255)]
                amber = [c.args for c in matrix.SetPixel.call_args_list
                         if c.args[2:] == (255, 160, 0)]
                self.assertTrue(blue)
                self.assertTrue(amber)
                self.assertTrue(all(0 <= x < 7 and height - 9 <= y < height
                                    for x, y, *_ in blue))


if __name__ == "__main__":
    unittest.main()
