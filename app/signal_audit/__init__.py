"""
The signal-candidate audit (docs/dev/specs/FDS-SIG-001-signal-candidate-audit.md) and
its round-one candidates (FDS-SIG-002).

On bars no one had seen when a round was registered, does a candidate call the next
bar's direction better than the best constant guess, by more than chance, once every
test in the round is accounted for, and does that hold again on the next fresh window?

* ``stats``: the tests of FDS-SIG-001 section 7, their dependence-robust p-values, Holm
  (section 8) and the power figures (section 9).
* ``candidates``: registered rules that call up, down or abstain at the close of a bar
  from closed bars only (section 5); SIG-A and SIG-B (FDS-SIG-002 section 3).
* ``pairs``: a row's eligible pairs, ties, skipped pairs and calls (section 6).
* ``engine``: every row's statistics, both Holm procedures, the verdicts (section 7.6),
  an independent re-derivation of each verdict, and confirmation rounds (section 8.3).
* ``ranking``: the coin ranking, exclusions and history check (section 10.1), for any
  exchange whose connector lists its markets and reports daily quote volume: the
  exchanges in Settings, the primary exchange first (owner, 2026-11-06).
* ``registration``: the registration record and every refusal of section 12, step 4.
* ``report``: the round's report and evidence (section 13).

The audit only reports. Nothing here is wired to a strategy, the trainer, the trader or
paper trading (section 14), and it places no order.
"""
