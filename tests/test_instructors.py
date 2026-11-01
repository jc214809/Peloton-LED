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
