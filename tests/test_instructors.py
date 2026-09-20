from peloton.instructors import instructor_name, merge_instructor_counts, top_instructors


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
    prior = {'Cody Rigsby': 5}
    workouts = [
        {'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Cody Rigsby'}}},
        {'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Robin Arzon'}}},
    ]
    merged = merge_instructor_counts(prior, workouts)
    assert merged == {'Cody Rigsby': 6, 'Robin Arzon': 1}
    # The prior dict is not mutated in place.
    assert prior == {'Cody Rigsby': 5}


def test_merge_instructor_counts_skips_incomplete_workouts():
    workouts = [{'status': 'IN_PROGRESS', 'ride': {'instructor': {'name': 'Cody Rigsby'}}}]
    assert merge_instructor_counts({}, workouts) == {}


def test_merge_instructor_counts_skips_workouts_without_an_instructor():
    workouts = [{'status': 'COMPLETE', 'ride': {}}]
    assert merge_instructor_counts({}, workouts) == {}


def test_top_instructors_ranks_by_count_then_name():
    counts = {'Robin Arzon': 3, 'Cody Rigsby': 5, 'Ally Love': 3}
    assert top_instructors(counts, limit=3) == [
        ('Cody Rigsby', 5), ('Ally Love', 3), ('Robin Arzon', 3),
    ]


def test_top_instructors_respects_limit():
    counts = {'A': 1, 'B': 2, 'C': 3, 'D': 4}
    assert top_instructors(counts, limit=2) == [('D', 4), ('C', 3)]


def test_top_instructors_empty_when_no_counts():
    assert top_instructors({}) == []
    assert top_instructors(None) == []
