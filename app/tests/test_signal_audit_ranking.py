"""FDS-SIG-001 section 10.1 and section 12, step 0: the 30-day quote volume a round is
ranked on (the PR #228 review, finding 1).

A market's 30 days are ranked only when every day is accounted for. A failed request,
a missing answer or a missing day refuses the ranking, with each market's error and
the exchange kept; a genuine zero is a volume; nothing is estimated or filled.

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


def market(pair, coin, status="TRADING", trading=None):
    return ListedMarket(
        pair,
        coin,
        coin,
        "USDT",
        status,
        status == "TRADING" if trading is None else trading,
    )


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
    assert len(ev.missing_days) == 20 and "while the exchange lists it as" in ev.detail
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


def test_a_listing_or_a_stop_within_the_period_is_established():
    new = market("NEWUSDT", "NEW")
    old = market("OLDUSDT", "OLD", status="BREAK")
    gone = market("GONEUSDT", "GONE", status="BREAK")
    ranked = rank(
        [new, old, gone],
        {
            new.pair: volume(new.pair, DAYS[20:]),  # listed on day 21, unbroken since
            old.pair: volume(old.pair, DAYS[:5]),  # stopped trading after day 5
            gone.pair: volume(gone.pair, ()),  # no bar, not trading
        },
    )
    by = {r.coin: r for r in ranked}
    assert by["NEW"].volume_status == ranking.LISTED_IN_SPAN and by["NEW"].days == 10
    assert by["NEW"].quote_volume_30d == pytest.approx(1000.0)
    assert by["OLD"].volume_status == ranking.STOPPED_IN_SPAN and by["OLD"].days == 5
    assert by["GONE"].volume_status == ranking.NOT_TRADING
    assert by["GONE"].quote_volume_30d == 0.0
    # a market that stopped while the exchange still lists it as trading: incomplete
    still = market("OLDUSDT", "OLD")
    with pytest.raises(ranking.RankingRefused):
        rank([still], {still.pair: volume(still.pair, DAYS[:5])})


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
