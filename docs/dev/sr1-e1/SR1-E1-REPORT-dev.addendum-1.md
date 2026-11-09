# SR1-E1 development report: addendum 1

Issued 2026-11-08. It corrects the wording of two verdict lines, S3 and S4, in `SR1-E1-REPORT-dev.md`. That report is sealed evidence and stays unchanged.

- **What changes:** the words of the S3 and S4 lines and of the note under family S's table.
- **What does not change:** every figure, test, p-value, outcome and verdict. S3 and S4 remain failed economic assessments.
- **How it was made:** `docs/dev/sr1_e1_addendum.py` renders the corrected lines from the same sealed results, with the corrected words in `strategy_lab.e1`. It checks these files first:

| File | SHA-256 |
|---|---|
| `results.json` | `697b09c700a986c6783539c17875107cc5032a7117abff68ad1bdafaf7c9fac7` |
| `experiment.json` | `9a095a5993295968b86d3ef7c12d9cf9b6a85ef12cd6468522fc547bfc1ad1b1` |
| `SR1-E1-REPORT-dev.md` | `6ab7821fb8c3e36fa351fb21f4eb47cdf22aed7d962d9103cecddda1bff78bc9` |

## Why

Each original line named the F3 requirement that was not met, but not that it failed. For example, "Not shown to be profitable after fees: a profit in each half" can be read as saying there was a profit in each half. The opposite is true: STRAT-004 lost money in the first half. Each original line also gave its bootstrap p-value, below 0.01, without saying in the line that this meets only one of F3's five requirements.

## The corrected lines

- **S3.** Not shown to be profitable after fees. STRAT-004 failed the requirement for a positive net profit in both evaluation halves (first half $-116.89, second half $+1,809.83). Its bootstrap test of return per capital-day passed Holm over 4 (p = 0.0086), but that is one of F3's five requirements, and a pass needs all five. Figures: net $+1,692.94 on £10,000, return per capital-day +0.2882%, 135 trades, maximum drawdown 7.32%, smallest detectable return per capital-day +0.5595%. Development only: not evidence for enabling anything.
- **S4.** Not shown to be profitable after fees. STRAT-005 exceeded the permitted 8% maximum drawdown, reaching 10.14%. Its bootstrap test of return per capital-day passed Holm over 4 (p = 0.0001), but that is one of F3's five requirements, and a pass needs all five. Figures: net $+1,528.33 on £10,000, return per capital-day +0.1683%, 151 trades, maximum drawdown 10.14%, smallest detectable return per capital-day +0.2586%. Development only: not evidence for enabling anything.

They replace these original lines:

- **S3.** Not shown to be profitable after fees: a profit in each half (net $+1,692.94 on £10,000, return per capital-day +0.2882%, 135 trades, maximum drawdown 7.32%, p = 0.0086 (Holm over 4), smallest detectable return per capital-day +0.5595%). Development only: not evidence for enabling anything.
- **S4.** Not shown to be profitable after fees: a drawdown below the halt level (net $+1,528.33 on £10,000, return per capital-day +0.1683%, 151 trades, maximum drawdown 10.14%, p = 0.0001 (Holm over 4), smallest detectable return per capital-day +0.2586%). Development only: not evidence for enabling anything.

## F3's five requirements, one by one

A pass needs all five. A bootstrap p-value that passes Holm meets the second requirement only.

| Member | Outcome | At least 100 trades and 30 in each half | Bootstrap test passes Holm | A positive net profit in both halves | A positive net profit without the most profitable coin | Maximum drawdown below the halt level |
|---|---|---|---|---|---|---|
| S3 | Fail | Met: 135 trades, 68 and 67 by half | Met: p = 0.0086, passes Holm over 4 | **Failed:** first half $-116.89, second half $+1,809.83 | Met: $+923.31 without SOL | Met: 7.32% against 8% |
| S4 | Fail | Met: 151 trades, 53 and 98 by half | Met: p = 0.0001, passes Holm over 4 | Met: first half $+174.18, second half $+1,354.15 | Met: $+1,110.50 without SOL | **Failed:** 10.14% against 8% |

## The same results on the account

Return per capital-day is the net profit divided by the capital-days: the dollars committed times the days they were held. It says nothing about the cash left idle. The whole account is shown next to it, because most of the account stayed in cash.

| Member | Strategy | Return per capital-day | Return on the account over the period | A year, on the account | Mean share of the account committed |
|---|---|---|---|---|---|
| S3 | STRAT-004 | +0.2882% | +12.56% | +2.76% | 2.64% |
| S4 | STRAT-005 | +0.1683% | +11.34% | +2.50% | 3.97% |

## The corrected note under family S's table

For S3 and S4 the day-block bootstrap is the family member, and "p passes Holm" is about it alone. It is one of F3's five requirements, and a pass needs all five: each line names the requirement that failed. With blocks of 896 days (section 2), that bootstrap carries little information.

Development only: not evidence for enabling anything.
