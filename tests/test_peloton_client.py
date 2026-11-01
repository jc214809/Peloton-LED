"""PelotonClient against a fake session: paging edge cases and bad responses."""
import json
import time
from unittest.mock import Mock

import pytest
import requests

from peloton.api import PelotonClient, make_session

NOW = int(time.time())


def _response(status=200, body=None):
    response = requests.Response()
    response.status_code = status
    response._content = body if isinstance(body, bytes) else json.dumps(body if body is not None else {}).encode()
    response.url = 'https://api.onepeloton.com/test'
    return response


def _client(*bodies):
    session = Mock()
    session.get.side_effect = [b if isinstance(b, requests.Response) else _response(body=b) for b in bodies]
    return PelotonClient(session), session


def _w(wid, age_days=0):
    return {'id': wid, 'created_at': NOW - int(age_days * 86400), 'status': 'COMPLETE'}


# make_session

def test_make_session_sends_the_bearer_token(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('  abc.def.ghi \n')
    session = make_session(token)
    assert session.headers['Authorization'] == 'Bearer abc.def.ghi'
    assert session.headers['peloton-platform'] == 'web'


def test_make_session_rejects_an_empty_token(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('\n')
    with pytest.raises(ValueError, match='empty'):
        make_session(token)


def test_close_closes_the_session():
    client, session = _client()
    client.close()
    session.close.assert_called_once()


# Bad responses

@pytest.mark.parametrize('method,args', [('get_me', ()), ('get_overview', ('u',)),
                                         ('get_workouts_page', ('u', 50))])
@pytest.mark.parametrize('body', [[], 'text', 5])
def test_non_object_json_is_rejected(method, args, body):
    client, _ = _client(body)
    with pytest.raises(ValueError, match='JSON object'):
        getattr(client, method)(*args)


def test_non_json_body_raises():
    client, _ = _client(_response(body=b'<html>maintenance</html>'))
    with pytest.raises(ValueError):
        client.get_me()


@pytest.mark.parametrize('status', [429, 500, 503])
def test_server_errors_raise_without_requesting_login(status):
    client, _ = _client(_response(status, {}))
    with pytest.raises(requests.HTTPError):
        client.get_overview('u')
    assert client.login_required is False


def test_perf_graph_missing_or_unreadable_is_none():
    client, _ = _client(_response(404, {}), _response(body=b'not json'), _response(body=[1, 2]))
    assert client.get_perf_graph('a') is None
    assert client.get_perf_graph('b') is None
    assert client.get_perf_graph('c') is None


def test_perf_graph_server_error_raises():
    client, _ = _client(_response(500, {}))
    with pytest.raises(requests.HTTPError):
        client.get_perf_graph('a')


def test_perf_graph_success():
    client, session = _client({'metrics': []})
    assert client.get_perf_graph('w1') == {'metrics': []}
    assert session.get.call_args.kwargs['params'] == {'every_n': 5}


# iter_workout_pages

def _pages(client, **kwargs):
    return [(number, [w['id'] for w in rows]) for number, rows, _ in client.iter_workout_pages('u', **kwargs)]


@pytest.mark.parametrize('kwargs', [{'page_size': 0}, {'page_size': 5, 'max_pages': 0},
                                    {'page_size': 5, 'start_page': -1}])
def test_pages_reject_bad_limits(kwargs):
    client, session = _client()
    with pytest.raises(ValueError, match='positive'):
        list(client.iter_workout_pages('u', **kwargs))
    session.get.assert_not_called()


@pytest.mark.parametrize('rows', [{'not': 'a list'}, ['not a dict']])
def test_pages_reject_malformed_pages(rows):
    client, _ = _client({'data': rows})
    with pytest.raises(ValueError, match='Malformed'):
        list(client.iter_workout_pages('u', page_size=5))


def test_pages_empty_history_is_one_empty_page():
    client, _ = _client({'data': []})
    assert _pages(client, page_size=5) == [(0, [])]


def test_pages_walk_until_show_next_is_false_with_the_page_sent():
    client, session = _client({'data': [_w('a'), _w('b')], 'show_next': True},
                              {'data': [_w('c')], 'show_next': False})
    assert _pages(client, page_size=2) == [(0, ['a', 'b']), (1, ['c'])]
    assert [c.kwargs['params'] for c in session.get.call_args_list] == [
        {'joins': 'ride,ride.instructor', 'limit': 2, 'page': 0},
        {'joins': 'ride,ride.instructor', 'limit': 2, 'page': 1}]


def test_pages_resume_from_a_start_page():
    client, session = _client({'data': [_w('c')], 'show_next': False})
    assert _pages(client, page_size=2, start_page=3) == [(3, ['c'])]
    assert session.get.call_args.kwargs['params']['page'] == 3


def test_pages_stop_at_page_count_and_short_pages():
    client, session = _client({'data': [_w('a'), _w('b')], 'page_count': 1, 'show_next': True})
    assert _pages(client, page_size=2) == [(0, ['a', 'b'])]
    client, session = _client({'data': [_w('a')]})
    assert _pages(client, page_size=50) == [(0, ['a'])]
    assert session.get.call_count == 1


def test_pages_stop_when_peloton_repeats_a_page(caplog):
    page = {'data': [_w('a')], 'show_next': True}
    client, _ = _client(page, page)
    assert _pages(client, page_size=1, max_pages=5) == [(0, ['a'])]
    assert 'repeated workout page' in caplog.text


def test_pages_stop_at_the_page_limit(caplog):
    client, session = _client({'data': [_w('a')], 'show_next': True})
    assert _pages(client, page_size=1, max_pages=1) == [(0, ['a'])]
    assert session.get.call_count == 1
    assert '1-page limit' in caplog.text


def test_pages_are_fetched_lazily():
    client, session = _client({'data': [_w('a')], 'show_next': True}, {'data': [_w('b')], 'show_next': False})
    for _ in client.iter_workout_pages('u', page_size=1):
        break
    assert session.get.call_count == 1
