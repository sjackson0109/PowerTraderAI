"""FDS-SIG-001 section 10.1 and section 12, step 0: the 30-day quote volume a round is
ranked on (the PR #228 review, finding 1, and its follow-up).

A market's 30 days are ranked only when every day is accounted for. A failed request,
a missing answer or a missing day refuses the ranking, with each market's error and
the exchange kept; a genuine zero is a volume; nothing is estimated or filled. A day
without a bar is accounted for only by the exchange's own stated trading start or end
(owner, D10): the same bars without a stated date look exactly like an incomplete
answer, and refuse.

No network: the connector answers are fixtures.
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from pt_exchange_abstraction import (  # noqa: E402
    DailyQuoteVolume,
    ListedMarket,
    MarketListing,
    RawAnswer,
)
from signal_audit import ranking  # noqa: E402

UTC = timezone.utc
DATE = "2026-11-06"
DAYS = ranking.ranking_days(DATE)


# --- quote volume ------------------------------------------------------------


def market(pair, coin, status="TRADING", trading=None, start=None, end=None):
    """A listed market; ``start`` and ``end`` (ms) are the exchange's stated trading
    start and end, from a listing field named for the test."""
    return ListedMarket(
        pair,
        coin,
        coin,
        "USDT",
        status,
        status == "TRADING" if trading is None else trading,
        trading_start_ms=start,
        trading_end_ms=end,
        history_stated_by="listingTimes" if start or end else "",
    )


H10 = 10 * 3_600_000  # a listing at 10:00 UTC, as KuCoin's are


def volume(pair, days, v=100.0):
    answer = RawAnswer(f"https://example.invalid/{pair}", (), 200, b"[]")
    return DailyQuoteVolume(
        "ex", pair, tuple((d, v) for d in days), "quote field", (answer,)
    )


def listing(*markets):
    return MarketListing("ex", "USDT", tuple(markets), ())


def rank(markets, vols):
    return ranking.rank_markets(listing(*markets), vols, DATE, ranking.Exclusions())


def test_every_day_present_is_complete_and_a_genuine_zero_is_a_volume():
    a, z = market("AAAUSDT", "AAA"), market("ZZZUSDT", "ZZZ")
    ranked = rank(
        [a, z], {a.pair: volume(a.pair, DAYS), z.pair: volume(z.pair, DAYS, 0.0)}
    )
    by = {r.coin: r for r in ranked}
    assert by["AAA"].volume_status == ranking.COMPLETE and by["AAA"].days == 30
    assert by["AAA"].quote_volume_30d == pytest.approx(3000.0)
    # a market that traded nothing on its 30 days: zero, stated, ranked last
    assert by["ZZZ"].volume_status == ranking.COMPLETE and by["ZZZ"].days == 30
    assert by["ZZZ"].quote_volume_30d == 0.0 and by["ZZZ"].included
    assert [r.coin for r in ranked] == ["AAA", "ZZZ"]


def test_a_failed_request_refuses_the_ranking_and_keeps_its_error():
    class Connector:
        def daily_quote_volume(self, pair, start_ms, end_ms):
            if pair == "BBBUSDT":
                raise TimeoutError("read timed out")
            if pair == "CCCUSDT":
                return None
            return volume(pair, DAYS)

    ms = [market("AAAUSDT", "AAA"), market("BBBUSDT", "BBB"), market("CCCUSDT", "CCC")]
    logged = []
    vols = ranking.gather_volumes(Connector(), "ex", listing(*ms), DAYS, logged.append)
    assert vols["BBBUSDT"] == ranking.VolumeFailure(
        "ex", "BBBUSDT", "TimeoutError: read timed out"
    )
    assert vols["CCCUSDT"].error == "the connector gave no answer"
    assert len(logged) == 2
    with pytest.raises(ranking.RankingRefused, match="2 included market") as info:
        rank(ms, vols)
    failed = {e.pair: e for e in info.value.markets}
    assert set(failed) == {"BBBUSDT", "CCCUSDT"}
    assert failed["BBBUSDT"].status == ranking.FAILED
    assert failed["BBBUSDT"].detail == "TimeoutError: read timed out"
    assert failed["BBBUSDT"].total is None and len(failed["BBBUSDT"].missing_days) == 30
    # the evidence is written as it is (run_signal_audit.rank: ranking/refused.json)
    json.dumps([e.to_dict() for e in info.value.markets])


def test_a_market_missing_from_the_answers_refuses_the_ranking():
    a, b = market("AAAUSDT", "AAA"), market("BBBUSDT", "BBB")
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a, b], {a.pair: volume(a.pair, DAYS)})
    assert [(e.pair, e.status, e.detail) for e in info.value.markets] == [
        ("BBBUSDT", ranking.FAILED, "no answer")
    ]


def test_an_incomplete_period_refuses_the_ranking():
    """The review's case: 10 of 30 days, ranked before on those 10 days alone."""
    a, c = market("AAAUSDT", "AAA"), market("CCCUSDT", "CCC")
    # days missing at the end while the market trades: incomplete
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a, c], {a.pair: volume(a.pair, DAYS), c.pair: volume(c.pair, DAYS[:10])})
    (ev,) = info.value.markets
    assert ev.status == ranking.INCOMPLETE and ev.days_present == 10
    assert len(ev.missing_days) == 20
    assert "states no trading start or end that accounts for them" in ev.detail
    # a gap inside the period: incomplete
    gapped = DAYS[:12] + DAYS[13:]
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a, c], {a.pair: volume(a.pair, DAYS), c.pair: volume(c.pair, gapped)})
    (ev,) = info.value.markets
    assert ev.status == ranking.INCOMPLETE
    assert ev.missing_days == [
        datetime.fromtimestamp(DAYS[12] / 1000, UTC).strftime("%Y-%m-%d")
    ]
    # no bar at all while trading: incomplete, not zero
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a, c], {a.pair: volume(a.pair, DAYS), c.pair: volume(c.pair, ())})
    assert info.value.markets[0].status == ranking.INCOMPLETE


def test_a_volume_that_is_not_a_number_refuses_the_ranking():
    a = market("AAAUSDT", "AAA")
    for bad in (float("nan"), float("inf"), -1.0):
        with pytest.raises(ranking.RankingRefused) as info:
            rank([a], {a.pair: volume(a.pair, DAYS, bad)})
        assert info.value.markets[0].status == ranking.FAILED


def test_a_genuine_recent_listing_is_established_from_its_stated_start():
    new = market("NEWUSDT", "NEW", start=DAYS[20] + H10)  # listed on day 21
    soon = market("SOONUSDT", "SOON", start=DAYS[-1] + 3 * 86_400_000)  # after the span
    ranked = rank(
        [new, soon],
        {new.pair: volume(new.pair, DAYS[20:]), soon.pair: volume(soon.pair, ())},
    )
    by = {r.coin: r for r in ranked}
    assert by["NEW"].volume_status == ranking.LISTED_IN_SPAN and by["NEW"].days == 10
    assert by["NEW"].quote_volume_30d == pytest.approx(1000.0)
    # the exchange's statement is kept with the ranking
    assert by["NEW"].stated_start == "2026-10-28T10:00:00Z"
    assert by["NEW"].stated_by == "listingTimes" and by["NEW"].stated_end is None
    assert by["SOON"].volume_status == ranking.LISTED_AFTER_SPAN
    assert by["SOON"].quote_volume_30d == 0.0


def test_the_same_bars_without_a_stated_start_are_an_incomplete_answer():
    """A first bar on day 21 is what a recent listing looks like, and what an answer
    that lost its first 20 days looks like: without the exchange's statement the
    ranking is refused (before the follow-up review, this ranked as listed)."""
    a = market("NEWUSDT", "NEW")
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a], {a.pair: volume(a.pair, DAYS[20:])})
    (ev,) = info.value.markets
    assert ev.status == ranking.INCOMPLETE and ev.first_bar == "2026-10-28"
    assert ev.stated_start is None and len(ev.missing_days) == 20


def test_a_stated_start_does_not_cover_days_missing_after_it():
    a = market("NEWUSDT", "NEW", start=DAYS[20] + H10)
    # the answer lost the listing's first three days
    with pytest.raises(ranking.RankingRefused) as info:
        rank([a], {a.pair: volume(a.pair, DAYS[23:])})
    (ev,) = info.value.markets
    assert ev.status == ranking.INCOMPLETE and "inside the trading period" in ev.detail
    # a gap after the listing
    with pytest.raises(ranking.RankingRefused):
        rank([a], {a.pair: volume(a.pair, DAYS[20:25] + DAYS[26:])})


def test_a_ceased_market_is_established_only_from_a_stated_end():
    old = market("OLDUSDT", "OLD", status="BREAK", end=DAYS[4] + H10)
    gone = market("GONEUSDT", "GONE", status="BREAK", end=DAYS[0] - 5 * 86_400_000)
    both = market(
        "BOTHUSDT", "BOTH", status="BREAK", start=DAYS[3] + H10, end=DAYS[9] + H10
    )
    ranked = rank(
        [old, gone, both],
        {
            old.pair: volume(old.pair, DAYS[:5]),  # stopped on day 5, as stated
            gone.pair: volume(gone.pair, ()),  # stopped before the span, as stated
            both.pair: volume(both.pair, DAYS[3:10]),
        },
    )
    by = {r.coin: r for r in ranked}
    assert by["OLD"].volume_status == ranking.STOPPED_IN_SPAN and by["OLD"].days == 5
    assert by["GONE"].volume_status == ranking.STOPPED_BEFORE_SPAN
    assert by["GONE"].quote_volume_30d == 0.0
    assert by["BOTH"].volume_status == ranking.LISTED_AND_STOPPED
    assert by["BOTH"].quote_volume_30d == pytest.approx(700.0)


def test_bars_ending_or_absent_without_a_stated_end_refuse_the_ranking():
    """The follow-up review's case: no later bars and a status of not trading say
    nothing of when trading stopped (before the follow-up, these ranked as stopped
    within the span and as not trading in it)."""
    old = market("OLDUSDT", "OLD", status="BREAK")
    with pytest.raises(ranking.RankingRefused) as info:
        rank([old], {old.pair: volume(old.pair, DAYS[:5])})
    assert info.value.markets[0].status == ranking.INCOMPLETE
    gone = market("GONEUSDT", "GONE", status="BREAK")
    with pytest.raises(ranking.RankingRefused) as info:
        rank([gone], {gone.pair: volume(gone.pair, ())})
    (ev,) = info.value.markets
    assert ev.status == ranking.INCOMPLETE and ev.total is None
    # a market that stopped while the exchange still lists it as trading
    still = market("OLDUSDT", "OLD")
    with pytest.raises(ranking.RankingRefused):
        rank([still], {still.pair: volume(still.pair, DAYS[:5])})


def test_evidence_that_conflicts_with_the_stated_times_refuses_the_ranking():
    cases = [
        # bars before the stated start
        (market("AUSDT", "A", start=DAYS[20] + H10), DAYS[15:], "before the stated"),
        # bars after the stated end
        (
            market("BUSDT", "B", status="BREAK", end=DAYS[4] + H10),
            DAYS[:8],
            "after the stated",
        ),
        # a stated end while the exchange lists the market as trading
        (market("CUSDT", "C", end=DAYS[4] + H10), DAYS[:5], "lists the market as"),
        # a stated end before the stated start
        (
            market("DUSDT", "D", status="BREAK", start=DAYS[9], end=DAYS[3]),
            DAYS[3:9],
            "precedes the stated start",
        ),
    ]
    for m, days, why in cases:
        with pytest.raises(ranking.RankingRefused) as info:
            rank([m], {m.pair: volume(m.pair, days)})
        (ev,) = info.value.markets
        assert ev.status == ranking.CONFLICTING and why in ev.detail, (m.pair, ev)
        json.dumps(ev.to_dict())  # kept as it is, stated times included


def test_complete_bars_need_no_stated_dates():
    a = market("AAAUSDT", "AAA", start=DAYS[0] - 400 * 86_400_000)
    (r,) = rank([a], {a.pair: volume(a.pair, DAYS)})
    assert r.volume_status == ranking.COMPLETE and r.stated_start is not None


def test_an_excluded_market_records_its_failure_without_refusing():
    a, usdc = market("AAAUSDT", "AAA"), market("USDCUSDT", "USDC")
    vols = {
        a.pair: volume(a.pair, DAYS),
        usdc.pair: ranking.VolumeFailure("ex", usdc.pair, "HTTPError: 500"),
    }
    by = {r.coin: r for r in rank([a, usdc], vols)}
    assert not by["USDC"].included and by["USDC"].volume_status == ranking.FAILED
    assert by["USDC"].volume_detail == "HTTPError: 500"


def test_the_ranking_fetch_comes_after_the_ranking_day_has_closed():
    day = datetime(2026, 11, 6, tzinfo=UTC)
    same_day = ranking.ranking_fetch_problem(DATE, day.replace(hour=15))
    assert "still forming" in same_day
    assert ranking.ranking_fetch_problem(DATE, datetime(2026, 11, 7, tzinfo=UTC)) == ""
    assert (
        ranking.ranking_fetch_problem(DATE, datetime(2026, 11, 13, 23, tzinfo=UTC))
        == ""
    )
    assert "more than 7 days" in ranking.ranking_fetch_problem(
        DATE, datetime(2026, 11, 14, tzinfo=UTC)
    )
