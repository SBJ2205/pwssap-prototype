"""Sanity checks for Phase 6's time-slot preference validation
(product decision #10): reject degenerate submissions outright, warn on
merely uninformative ones.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_preferences_validation
"""
from domain.enums import PreferenceRating
from domain.timeslots import build_canonical_grid, is_slot_usable
from domain.validation import validate_time_slot_preferences

RATABLE_KEYS = {s.key for s in build_canonical_grid() if is_slot_usable(s)}

PREFERRED = PreferenceRating.PREFERRED.value
TOLERABLE = PreferenceRating.TOLERABLE.value
DISLIKED = PreferenceRating.DISLIKED.value
BLOCKED = PreferenceRating.BLOCKED.value


def test_ratable_grid_has_19_slots():
    assert len(RATABLE_KEYS) == 19  # 20 canonical slots minus Mon-1


def test_empty_ratings_is_rejected():
    result = validate_time_slot_preferences({}, RATABLE_KEYS)
    assert not result.is_valid
    assert result.warnings == []


def test_unknown_slot_key_is_rejected():
    result = validate_time_slot_preferences({"Mon-1": PREFERRED}, RATABLE_KEYS)  # Mon-1 isn't ratable
    assert not result.is_valid
    assert any("Mon-1" in e for e in result.errors)


def test_out_of_range_rating_value_is_rejected():
    keys = list(RATABLE_KEYS)
    result = validate_time_slot_preferences({keys[0]: 9}, RATABLE_KEYS)
    assert not result.is_valid


def test_mostly_blocked_is_rejected_outright():
    keys = list(RATABLE_KEYS)
    ratings = {k: BLOCKED for k in keys[:15]}  # 15/19 > 70%
    result = validate_time_slot_preferences(ratings, RATABLE_KEYS)
    assert not result.is_valid
    assert result.warnings == []


def test_well_spread_ratings_produce_no_errors_or_warnings():
    keys = list(RATABLE_KEYS)
    ratings = {}
    for i, k in enumerate(keys):
        ratings[k] = [PREFERRED, TOLERABLE, DISLIKED][i % 3]
    result = validate_time_slot_preferences(ratings, RATABLE_KEYS)
    assert result.is_valid
    assert result.warnings == []


def test_mostly_low_preference_but_below_block_threshold_warns():
    keys = list(RATABLE_KEYS)
    ratings = {}
    for k in keys[:3]:
        ratings[k] = BLOCKED
    for k in keys[3:8]:
        ratings[k] = DISLIKED
    for k in keys[8:10]:
        ratings[k] = PREFERRED
    # rated_count=10, low_count=8 (3 blocked + 5 disliked) -> 80% low
    result = validate_time_slot_preferences(ratings, RATABLE_KEYS)
    assert result.is_valid
    assert any("Disliked or Blocked" in w for w in result.warnings)


def test_uniform_rating_across_enough_slots_warns():
    keys = list(RATABLE_KEYS)[:6]
    ratings = {k: TOLERABLE for k in keys}
    result = validate_time_slot_preferences(ratings, RATABLE_KEYS)
    assert result.is_valid
    assert any("rated every slot the same" in w for w in result.warnings)
    assert not any("Disliked or Blocked" in w for w in result.warnings)


def test_uniform_rating_with_too_few_slots_does_not_warn():
    keys = list(RATABLE_KEYS)[:3]  # below UNIFORM_WARN_MIN_RATED
    ratings = {k: TOLERABLE for k in keys}
    result = validate_time_slot_preferences(ratings, RATABLE_KEYS)
    assert result.is_valid
    assert result.warnings == []


def _run_all():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_all()
