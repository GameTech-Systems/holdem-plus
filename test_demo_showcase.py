"""
Tests for demo_showcase.py.

Run with: pytest -v test_demo_showcase.py
"""

from demo_showcase import (
    _build_extra_card_showcase,
    _build_rabbit_hunt_showcase,
    build_demo_script,
    serialize_demo_script,
)


# ---------------------------------------------------------------------------
# Showcase hand 1: "The Extra Card"
# ---------------------------------------------------------------------------

def test_extra_card_showcase_kai_wins_with_a_straight():
    demo = _build_extra_card_showcase()
    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert result.payouts == {"Kai": 6}


def test_extra_card_showcase_deals_two_then_three_hole_cards():
    demo = _build_extra_card_showcase()
    deal_event = demo.events[0]
    assert deal_event.kind == "deal"
    assert all(len(p["hole_cards"]) == 2 for p in deal_event.players)

    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert all(len(p["hole_cards"]) == 3 for p in result.players)


def test_extra_card_showcase_conserves_chips():
    demo = _build_extra_card_showcase()
    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert sum(p["stack"] for p in result.players) == 600  # 3 * 200 starting stacks


def test_extra_card_showcase_reaches_a_real_showdown_not_a_fold():
    demo = _build_extra_card_showcase()
    assert not any(e.action == "FOLD" for e in demo.events)
    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert not any(p["folded"] for p in result.players)


def test_extra_card_showcase_highlights_the_third_card_moment_and_the_payoff():
    demo = _build_extra_card_showcase()
    highlighted = [e for e in demo.events if e.highlight]
    assert len(highlighted) == 2
    assert any("3rd hole card" in e.narration for e in highlighted)
    assert any(e.kind == "hand_result" for e in highlighted)


def test_extra_card_showcase_board_is_revealed_in_three_stages():
    demo = _build_extra_card_showcase()
    reveal_lengths = [len(e.community_cards) for e in demo.events if e.kind == "reveal"]
    assert reveal_lengths == [3, 4, 5]


# ---------------------------------------------------------------------------
# Showcase hand 2: "Rabbit Runner"
# ---------------------------------------------------------------------------

def test_rabbit_hunt_showcase_rio_folds_on_the_turn():
    demo = _build_rabbit_hunt_showcase()
    fold_events = [e for e in demo.events if e.action == "FOLD"]
    assert len(fold_events) == 1
    assert fold_events[0].actor == "Rio"
    # the fold happens right after the turn reveal (4 community cards), not
    # after a 5th (river) has been shown -- confirms this is genuinely a
    # turn fold, the exact scenario Rabbit Runner eligibility requires
    assert len(fold_events[0].community_cards) == 4


def test_rabbit_hunt_showcase_sam_wins_uncontested():
    demo = _build_rabbit_hunt_showcase()
    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert result.payouts == {"Sam": 10}


def test_rabbit_hunt_showcase_reveals_a_river_card():
    demo = _build_rabbit_hunt_showcase()
    reveals = [e for e in demo.events if e.kind == "rabbit_hunt"]
    assert len(reveals) == 1
    assert reveals[0].revealed_card is not None
    assert "river" in reveals[0].narration.lower()
    # the real board (not the peeked river) still only shows 4 cards --
    # rabbit-hunting doesn't retroactively make the fold-ended hand's
    # public board 5 cards
    assert len(reveals[0].community_cards) == 4


def test_rabbit_hunt_showcase_fee_is_the_only_chip_discrepancy():
    demo = _build_rabbit_hunt_showcase()
    result = [e for e in demo.events if e.kind == "hand_result"][0]
    assert sum(p["stack"] for p in result.players) == 400  # 2 * 200, before the fee

    reveal = [e for e in demo.events if e.kind == "rabbit_hunt"][0]
    # exactly one small blind "disappears" here -- see
    # orchestrator.Hand.rabbit_hunt's own docstring: the fee isn't
    # modeled as going anywhere in this fake-money demo, so this is
    # expected, not a bug in the showcase script.
    assert sum(p["stack"] for p in reveal.players) == 399


# ---------------------------------------------------------------------------
# build_demo_script / serialize_demo_script
# ---------------------------------------------------------------------------

def test_build_demo_script_returns_both_showcase_hands_in_order():
    hands = build_demo_script()
    assert [h.title for h in hands] == ["The Extra Card", "Rabbit Runner"]


def test_every_hand_ends_with_a_hand_result_event():
    for hand in build_demo_script():
        assert any(e.kind == "hand_result" for e in hand.events)


def test_build_demo_script_is_deterministic_across_calls():
    """No RNG anywhere in this module -- the whole point is that it's the
    same every time the demo endpoint is hit."""
    first = serialize_demo_script(build_demo_script())
    second = serialize_demo_script(build_demo_script())
    assert first == second


def test_serialize_demo_script_is_json_safe_shape():
    hands = build_demo_script()
    serialized = serialize_demo_script(hands)
    assert len(serialized) == 2
    for hand in serialized:
        assert set(hand.keys()) == {"title", "summary", "events"}
        for event in hand["events"]:
            assert isinstance(event["narration"], str)
            assert isinstance(event["community_cards"], list)
            assert isinstance(event["players"], list)
            for p in event["players"]:
                assert isinstance(p["hole_cards"], list)
                assert all(isinstance(c, str) for c in p["hole_cards"])
