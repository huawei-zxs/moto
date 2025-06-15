import json

import pytest

from moto.events.models import EventPattern


def test_event_pattern_with_allowed_values_event_filter():
    pattern = EventPattern.load(json.dumps({"source": ["foo", "bar"]}))
    assert pattern.matches_event({"source": "foo"})
    assert pattern.matches_event({"source": "bar"})
    assert not pattern.matches_event({"source": "baz"})


def test_event_pattern_with_nested_event_filter():
    pattern = EventPattern.load(json.dumps({"detail": {"foo": ["bar"]}}))
    assert pattern.matches_event({"detail": {"foo": "bar"}})
    assert not pattern.matches_event({"detail": {"foo": "baz"}})
    # The full list should match as well
    assert pattern.matches_event({"detail": {"foo": ["bar"]}})


def test_event_pattern_with_exists_event_filter():
    foo_exists = EventPattern.load(json.dumps({"detail": {"foo": [{"exists": True}]}}))
    assert foo_exists.matches_event({"detail": {"foo": "bar"}})
    assert foo_exists.matches_event({"detail": {"foo": None}})
    assert not foo_exists.matches_event({"detail": {}})
    # exists filters only match leaf nodes of an event
    assert not foo_exists.matches_event({"detail": {"foo": {"bar": "baz"}}})

    foo_not_exists = EventPattern.load(
        json.dumps({"detail": {"foo": [{"exists": False}]}})
    )
    assert not foo_not_exists.matches_event({"detail": {"foo": "bar"}})
    assert not foo_not_exists.matches_event({"detail": {"foo": None}})
    assert foo_not_exists.matches_event({"detail": {}})
    assert foo_not_exists.matches_event({"detail": {"foo": {"bar": "baz"}}})

    bar_exists = EventPattern.load(json.dumps({"detail": {"bar": [{"exists": True}]}}))
    assert not bar_exists.matches_event({"detail": {"foo": "bar"}})
    assert not bar_exists.matches_event({"detail": {}})

    bar_not_exists = EventPattern.load(
        json.dumps({"detail": {"bar": [{"exists": False}]}})
    )
    assert bar_not_exists.matches_event({"detail": {"foo": "bar"}})
    assert bar_not_exists.matches_event({"detail": {}})


def test_event_pattern_with_prefix_event_filter():
    pattern = EventPattern.load(json.dumps({"detail": {"foo": [{"prefix": "bar"}]}}))
    assert pattern.matches_event({"detail": {"foo": "bar"}})
    assert pattern.matches_event({"detail": {"foo": "bar!"}})
    assert not pattern.matches_event({"detail": {"foo": "ba"}})


@pytest.mark.parametrize(
    "operator, compare_to, should_match, should_not_match",
    [
        ("<", 1, [0], [1, 2]),
        ("<=", 1, [0, 1], [2]),
        ("=", 1, [1], [0, 2]),
        (">", 1, [2], [0, 1]),
        (">=", 1, [1, 2], [0]),
    ],
)
def test_event_pattern_with_single_numeric_event_filter(
    operator, compare_to, should_match, should_not_match
):
    pattern = EventPattern.load(
        json.dumps({"detail": {"foo": [{"numeric": [operator, compare_to]}]}})
    )
    for number in should_match:
        assert pattern.matches_event({"detail": {"foo": number}})
    for number in should_not_match:
        assert not pattern.matches_event({"detail": {"foo": number}})


def test_event_pattern_with_multi_numeric_event_filter():
    events = [{"detail": {"foo": number}} for number in range(5)]

    one_or_two = EventPattern.load(
        json.dumps({"detail": {"foo": [{"numeric": [">=", 1, "<", 3]}]}})
    )
    assert not one_or_two.matches_event(events[0])
    assert one_or_two.matches_event(events[1])
    assert one_or_two.matches_event(events[2])
    assert not one_or_two.matches_event(events[3])
    assert not one_or_two.matches_event(events[4])

    two_or_three = EventPattern.load(
        json.dumps({"detail": {"foo": [{"numeric": [">", 1, "<=", 3]}]}})
    )
    assert not two_or_three.matches_event(events[0])
    assert not two_or_three.matches_event(events[1])
    assert two_or_three.matches_event(events[2])
    assert two_or_three.matches_event(events[3])
    assert not two_or_three.matches_event(events[4])


@pytest.mark.parametrize(
    "pattern, expected_str",
    [('{"source": ["foo", "bar"]}', '{"source": ["foo", "bar"]}'), (None, None)],
)
def test_event_pattern_dump(pattern, expected_str):
    event_pattern = EventPattern.load(pattern)
    assert event_pattern.dump() == expected_str


def test_event_pattern_with_odd_length_numeric_filter():
    """Odd-length numeric filter arrays expose a bug where zip_longest
    with fillvalue=0 incorrectly adds a comparison against 0, creating
    a logical contradiction that prevents any match.

    For odd-length filter [">", 1, "<="]:
    - Buggy code: checks "> 1 AND <= 0" => contradiction, never matches
    - Correct code (zip): only checks "> 1", drops the trailing "<="
    """
    # FAIL_TO_PASS: These SHOULD match (values > 1) but bug prevents it
    pattern = EventPattern.load(
        json.dumps({"detail": {"foo": [{"numeric": [">", 1, "<="]}]}})
    )
    # Under correct code: only "> 1" is checked, so 2, 100, etc. match
    # Under buggy code: "> 1 AND <= 0" is checked, so nothing can match
    assert pattern.matches_event({"detail": {"foo": 2}})
    assert pattern.matches_event({"detail": {"foo": 100}})

    # PASS_TO_PASS: These correctly do NOT match under both behaviors
    assert not pattern.matches_event({"detail": {"foo": 1}})
    assert not pattern.matches_event({"detail": {"foo": 0}})

    # Additional test with trailing operator that would never match with fillvalue=0
    pattern2 = EventPattern.load(
        json.dumps({"detail": {"val": [{"numeric": ["<", 10, ">="]}]}})
    )
    # Under correct code: only "< 10" is checked
    assert pattern2.matches_event({"detail": {"val": 5}})
    assert not pattern2.matches_event({"detail": {"val": 10}})
    assert not pattern2.matches_event({"detail": {"val": 15}})
