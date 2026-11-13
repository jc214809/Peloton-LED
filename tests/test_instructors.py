from peloton.instructors import instructor_name, merge_instructor_counts, top_instructors


def _class(identity, name, status='COMPLETE', **extra):
    return {'status': status, 'ride': {'instructor': {'id': identity, 'name': name, **extra}}}


def test_instructor_name_prefers_name_over_display_name():
    workout = {'ride': {'instructor': {'name': 'Cody Rigsby', 'display_name': 'Cody'}}}
    assert instructor_name(workout) == 'Cody Rigsby'


def test_instructor_name_falls_back_to_display_name():
    workout = {'ride': {'instructor': {'display_name': 'Cody'}}}
    assert instructor_name(workout) == 'Cody'


def test_instructor_name_is_empty_string_when_missing():
    assert instructor_name({}) == ''
    assert instructor_name({'ride': {}}) == ''
    assert instructor_name({'ride': {'instructor': None}}) == ''


def test_merge_instructor_counts_adds_new_completed_workouts():
    prior_counts, prior_names = {'cody': 5}, {'cody': 'Cody Rigsby'}
    counts, names = merge_instructor_counts(prior_counts, prior_names, [
        _class('cody', 'Cody Rigsby'), _class('robin', 'Robin Arzón')])
    assert counts == {'cody': 6, 'robin': 1}
    assert names == {'cody': 'Cody Rigsby', 'robin': 'Robin Arzón'}
    # The prior dicts are not mutated in place.
    assert prior_counts == {'cody': 5} and prior_names == {'cody': 'Cody Rigsby'}


def test_merge_instructor_counts_skips_incomplete_workouts():
    assert merge_instructor_counts({}, {}, [_class('cody', 'Cody Rigsby', 'IN_PROGRESS')]) == ({}, {})


def test_merge_instructor_counts_skips_workouts_without_an_instructor():
    assert merge_instructor_counts({}, {}, [{'status': 'COMPLETE', 'ride': {}}, {'status': 'COMPLETE'}]) == ({}, {})


def test_placeholder_instructors_without_an_id_are_not_counted():
    # Regression: Peloton labels classless workouts with a fake instructor
    # ("JUST WALK" was Jen's #2 instructor with 231 "classes").
    placeholders = [_class(None, name) for name in (
        'JUST WALK', 'JUST RIDE', 'LANEBREAK', 'ENTERTAINMENT', 'OUTPUT GOAL', '24 MIN 6 SEC WALKING')]
    placeholders.append({'status': 'COMPLETE', 'ride': {'instructor': {'id': '', 'name': 'JUST RUN'}}})
    assert merge_instructor_counts({}, {}, placeholders) == ({}, {})


def test_group_classes_count_once_for_each_member():
    group = _class('pair', 'Jess & Selena', is_instructor_group=True,
                   individual_instructor_ids=['jess', 'selena', 'jess', 7])
    counts, names = merge_instructor_counts({}, {}, [group, _class('jess', 'Jess Sims')])
    assert counts == {'jess': 2, 'selena': 1}
    assert names == {'jess': 'Jess Sims'}  # the group's own name is never a contender
    # Selena is ranked once a solo class names her, even in a later batch.
    counts, names = merge_instructor_counts(counts, names, [_class('selena', 'Selena Samuela')])
    assert top_instructors(counts, names) == [('Jess Sims', 2), ('Selena Samuela', 2)]


def test_group_class_without_members_counts_for_nobody():
    for members in (None, 'jess', []):
        group = _class('pair', 'Multiple Instructors', is_instructor_group=True,
                       individual_instructor_ids=members)
        assert merge_instructor_counts({}, {}, [group]) == ({}, {})


def test_top_instructors_ranks_by_count_then_name():
    counts = {'r': 3, 'c': 5, 'a': 3}
    names = {'r': 'Robin Arzon', 'c': 'Cody Rigsby', 'a': 'Ally Love'}
    assert top_instructors(counts, names, limit=3) == [
        ('Cody Rigsby', 5), ('Ally Love', 3), ('Robin Arzon', 3),
    ]


def test_top_instructors_respects_limit_and_skips_unnamed_ids():
    counts = {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'unknown': 9}
    names = {key: key.upper() for key in 'abcd'}
    assert top_instructors(counts, names, limit=2) == [('D', 4), ('C', 3)]


def test_top_instructors_empty_when_no_counts():
    assert top_instructors({}, {}) == []
    assert top_instructors(None, None) == []


# --- class_numbers: which class this is with each instructor (instructor milestones) ---

def _row(instructor, start, status='COMPLETE', group=None, tz='America/New_York'):
    return {'instructor_id': instructor, 'group_ids': group, 'start': start, 'status': status, 'tz': tz}


def test_class_numbers_counts_earlier_completed_classes_plus_this_one():
    from peloton.instructors import class_numbers
    rows = {'a': _row('jess', 100), 'b': _row('jess', 200), 'c': _row('cody', 150),
            'd': _row('jess', 250, status='IN_PROGRESS'), 'later': _row('jess', 900)}
    numbers = class_numbers(rows, 'now', _row('jess', 500), {'jess': 'Jess Sims'})
    assert [(c['name'], c['n']) for c in numbers] == [('Jess Sims', 3)]


def test_class_numbers_does_not_count_the_workout_twice_or_move_when_later_ones_arrive():
    from peloton.instructors import class_numbers
    rows = {'a': _row('jess', 100), 'me': _row('jess', 500)}
    assert class_numbers(rows, 'me', rows['me'], {'jess': 'J'})[0]['n'] == 2
    rows['z'] = _row('jess', 600)
    assert class_numbers(rows, 'me', rows['me'], {'jess': 'J'})[0]['n'] == 2


def test_class_numbers_same_start_breaks_the_tie_by_id():
    from peloton.instructors import class_numbers
    rows = {'a': _row('jess', 500), 'c': _row('jess', 500)}
    assert class_numbers(rows, 'b', _row('jess', 500), {})[0]['n'] == 2


def test_class_numbers_group_classes_count_for_each_member():
    from peloton.instructors import class_numbers
    rows = {'a': _row('jess', 100), 'b': _row('selena', 120), 'g': _row('jess-selena', 130, group=['jess', 'selena'])}
    now = _row('jess-selena', 500, group=['jess', 'selena'])
    numbers = class_numbers(rows, 'now', now, {'jess': 'Jess Sims'})
    assert [(c['id'], c['n'], c['name']) for c in numbers] == [('jess', 3, 'Jess Sims'), ('selena', 3, None)]


def test_class_numbers_since_is_the_first_class_in_the_workouts_zone():
    from peloton.instructors import class_numbers
    first = 1551500000  # 2019-03-02 04:53 UTC = 2019-03-01 23:53 in New York
    rows = {'a': _row('jess', first), 'b': _row('jess', first + 10)}
    assert class_numbers(rows, 'now', _row('jess', first + 99), {})[0]['since'] == '2019-03-01'
    assert class_numbers(rows, 'now', _row('jess', first + 99, tz=None), {})[0]['since'] == '2019-03-02'
    assert class_numbers(rows, 'now', _row('jess', first + 99, tz='Not/AZone'), {})[0]['since'] == '2019-03-02'


def test_class_numbers_is_empty_without_an_instructor_or_a_start():
    from peloton.instructors import class_numbers
    assert class_numbers({}, 'now', _row(None, 5), {}) == []
    assert class_numbers({}, 'now', _row('', 5), {}) == []
    assert class_numbers({}, 'now', _row('jess', None), {}) == []
    assert class_numbers({}, 'now', _row('jess', True), {}) == []


def test_class_numbers_ignores_damaged_log_rows():
    from peloton.instructors import class_numbers
    rows = {'a': 'junk', 'b': _row('jess', None), 'c': _row('jess', 'soon'), 'd': _row('jess', 10, group=[None, 7]),
            'e': _row('jess', 20)}
    assert class_numbers(rows, 'now', _row('jess', 500), {})[0]['n'] == 2
