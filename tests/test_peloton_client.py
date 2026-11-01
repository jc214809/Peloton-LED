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


# get_recent_workouts

@pytest.mark.parametrize('kwargs', [{'limit': 0}, {'days': 0}, {'page_size': 0}, {'max_pages': -1}])
def test_recent_rejects_non_positive_limits(kwargs):
    client, session = _client()
    with pytest.raises(ValueError, match='positive'):
        client.get_recent_workouts('u', **kwargs)
    session.get.assert_not_called()


@pytest.mark.parametrize('rows', [{'not': 'a list'}, ['not a dict']])
def test_recent_rejects_malformed_pages(rows):
    client, _ = _client({'data': rows})
    with pytest.raises(ValueError, match='Malformed'):
        client.get_recent_workouts('u')


def test_recent_empty_history():
    client, _ = _client({'data': []})
    assert client.get_recent_workouts('u') == []
    assert client.history_truncated is False


def test_recent_skips_undated_and_old_workouts_but_keeps_paging():
    client, _ = _client({'data': [_w('a'), {'id': 'undated'}, _w('old', 200)], 'show_next': True},
                        {'data': [_w('b', 1)], 'show_next': False})
    assert [w['id'] for w in client.get_recent_workouts('u', days=90, page_size=3)] == ['a', 'b']


def test_recent_stops_at_the_workout_limit():
    client, _ = _client({'data': [_w('a'), _w('b'), _w('c')], 'show_next': True})
    assert [w['id'] for w in client.get_recent_workouts('u', limit=2)] == ['a', 'b']
    assert client.history_truncated is True


def test_recent_stops_at_page_count():
    client, session = _client({'data': [_w('a'), _w('b')], 'page_count': 1, 'show_next': True})
    assert len(client.get_recent_workouts('u', page_size=2)) == 2
    assert session.get.call_count == 1


def test_recent_short_page_without_show_next_is_the_end():
    client, session = _client({'data': [_w('a')]})
    assert len(client.get_recent_workouts('u', page_size=50)) == 1
    assert session.get.call_count == 1


def test_recent_page_limit_marks_history_truncated():
    client, _ = _client({'data': [_w('a')], 'show_next': True}, {'data': [_w('b')], 'show_next': True})
    assert len(client.get_recent_workouts('u', page_size=1, max_pages=2)) == 2
    assert client.history_truncated is True


def test_recent_workouts_without_ids_are_kept():
    anonymous = {'created_at': NOW, 'status': 'COMPLETE'}
    client, _ = _client({'data': [anonymous, dict(anonymous)], 'show_next': False})
    assert len(client.get_recent_workouts('u')) == 2


# get_all_workouts

@pytest.mark.parametrize('kwargs', [{'page_size': 0}, {'max_pages': 0}])
def test_all_rejects_non_positive_limits(kwargs):
    client, _ = _client()
    with pytest.raises(ValueError, match='positive'):
        client.get_all_workouts('u', **kwargs)


def test_all_rejects_malformed_pages():
    client, _ = _client({'data': 'nope'})
    with pytest.raises(ValueError, match='Malformed'):
        client.get_all_workouts('u')


def test_all_empty_and_short_pages_end_the_walk():
    client, _ = _client({'data': []})
    assert client.get_all_workouts('u') == []
    client, session = _client({'data': [_w('a')]})
    assert len(client.get_all_workouts('u', page_size=50)) == 1
    assert session.get.call_count == 1


def test_all_stops_at_page_count_and_deduplicates():
    client, _ = _client({'data': [_w('a'), _w('a')], 'page_count': 1, 'show_next': True})
    assert [w['id'] for w in client.get_all_workouts('u', page_size=2)] == ['a']


def test_all_repeated_page_and_page_limit_mark_truncated():
    page = {'data': [_w('a')], 'show_next': True}
    client, _ = _client(page, page)
    assert len(client.get_all_workouts('u', page_size=1, max_pages=5)) == 1
    assert client.history_truncated is True
    client, _ = _client({'data': [_w('a')], 'show_next': True})
    client.get_all_workouts('u', page_size=1, max_pages=1)
    assert client.history_truncated is True
