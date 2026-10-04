# Run log — issue templates

Replace the GitHub issue templates with one issue form per type (bug, feature, task), remove the
duplicates and the public security templates, and point security reports to private reporting.

Branch `chore/issue-templates` from `main` at `d815910`, in its own worktree
(`..\PowerTraderAI-templates`). Nothing under `app/` is changed.

## Phase 0 — inventory (read-only)

### Issue templates on `main` (all markdown, all removed)

| File | Name | Title prefix | Labels it applied |
| --- | --- | --- | --- |
| `bug_report.md` | 🐛 Bug Report | `[BUG] ` | `bug`, `needs-triage` |
| `bug-report.md` | 🐛 Bug Report (duplicate) | `[BUG] ` | `bug`, `needs-triage` |
| `feature_request.md` | ✨ Feature Request | `[FEATURE] ` | `enhancement`, `needs-discussion` |
| `feature-request.md` | ✨ Feature Request (duplicate) | `[FEATURE] ` | `enhancement`, `needs-triage` |
| `security_issue.md` | 🚨 Security Issue | `[SECURITY] ` | `security`, `critical` |
| `security-issue.md` | 🚨 Security Issue (duplicate) | `[SECURITY] ` | `security`, `priority-high` |
| `general_issue.md` | 📋 General Issue | `[ISSUE] ` | `question`, `needs-triage` |
| `development-task.md` | 🔧 Development Task | `[TASK] ` | `task`, `development` |
| `code_quality.md` | Code Quality Improvement | `[CODE QUALITY] ` | `code-quality`, `technical-debt`, `needs-discussion` |

Besides the three known duplicate pairs, `general_issue.md`, `development-task.md` and
`code_quality.md` all overlap the new "General issue / task" form, so they are removed too. Exactly
three templates remain.

`config.yml` already had `blank_issues_enabled: false`, but both contact links pointed to the upstream
repo (`PowerTrader-AI/PowerTrader_AI` Discussions and Wiki), not this one.

### Other files

* `.github/pull_request_template.md`: present, not changed. There is no `.github/PULL_REQUEST_TEMPLATE/`
  folder.
* `SECURITY.md`: missing (not at the root, in `docs/` or in `.github/`). `docs/security/README.md` is a
  user guide and says nothing about reporting vulnerabilities. A short `SECURITY.md` is added.

### Repository settings (read with `gh api`)

* Discussions: **enabled**, so the "Questions and ideas" link works.
* Private vulnerability reporting: **disabled** (`{"enabled": false}`). Until the owner turns it on, the
  "Security vulnerability" link and `SECURITY.md` lead to a page reporters can't use. Not changed here:
  it is a repository setting. See "Owner steps".
* The repo is a public fork of `garagesteve1155/PowerTrader_AI`.

### Labels

The 64 labels in the repo (`gh label list`) include `bug`, `enhancement`, `documentation`, `question`,
`security`, `code-quality`, `refactoring`, `testing`, the `priority-*`, `phase-*` and `component-*`
sets, and others. The new forms use only:

* `bug` (bug report)
* `enhancement` (feature request)

The task form has no label. No existing label covers every task type.

Labels I would have wanted but which don't exist (not created):

* `task`: for the "General issue / task" form. The old `development-task.md` already applied it, so
  those issues got no label.
* `needs-triage`: to mark new reports until someone has looked at them. `.github/PROJECT_SETUP.md`
  documents it, and three old templates applied it, but it was never created.

Other labels the old templates applied that don't exist: `needs-discussion`, `development`,
`technical-debt`, `critical`.

### Exchanges (for the bug report dropdown)

`app/pt_exchanges.py` registers 23 exchange classes with `ExchangeFactory`, and the README says "65+".
Most of them are placeholders: `place_order` raises `NotImplementedError` in every class except
`BinanceExchange` and three DeFi classes (Aave, Yearn Finance, Lido Finance, not checked further).
Live orders go through `trading_mode.resolve_order_target` → `ExchangeFactory`, so of the exchanges
below only Binance (with testnet) can place orders today.

The dropdown lists the five exchanges the product actually sets up: they are the ones with setup steps
in `app/exchange_setup.py` and in the Hub's "Primary exchange" list, and they have real
connection or market-data code:

* Binance: full connector, live and testnet orders.
* Coinbase: connection test (`check_connection`) and public prices.
* Kraken: public prices.
* KuCoin: public prices; also the trainer/thinker's fallback data source (`pt_data_provider`).
* Robinhood: setup wizard and a market-data call; no order methods.

Plus "Other" and "Not applicable". Bitstamp, Bybit and OKX appear in the Hub's list but have no
connector class at all, so they fall under "Other".

### References to the old template files

* `.github/DEVELOPMENT_WORKFLOW.md` line 104: "Create GitHub issue using development-task template".
  Updated to the new form.
* `QUICK_START.md` links to the `.github/ISSUE_TEMPLATE/` folder, which still exists. No change.
* `docs/troubleshooting/README.md` has its own inline "Issue Template" text block, not a link to a
  file. No change.
* `scripts/README.md` "Issue template formats" means the issue text written by
  `create_github_issues.py`, not these files. No change.
* No workflow names a template file.

### Auto-labelling workflow (`.github/workflows/project-management.yml`)

On every new issue, this workflow adds labels by matching words in the lower-cased title and body. An
issue form's body holds the field labels, chosen options and checkbox labels (markdown blocks and
descriptions aren't included). So these forms keep the trigger words out of their field and option
labels:

* `security` → `priority-critical`, `security` and `phase-1-critical` (the `security` label also
  triggers the "SECURITY ISSUE DETECTED" job, which adds `urgent`).
* `credential` → `component-security`.
* `stability` / `functional` / `production` / `optimization` → a `phase-*` label.

Title prefixes still match: `[Bug]: ` → `priority-high`, `[Feature]: ` → `priority-medium`.

Kept, as with the old templates: the bug report's "Trading mode" field and the feature request's
"Does this affect live trading or risk?" field both contain "trading", so bug reports and feature
requests get `component-trading` (unless the text mentions credentials, which wins). The old bug and
feature templates did this too ("Trading Impact"). Changing that needs a change to the workflow, which
this task doesn't touch.

## Phase 1 — the forms (commit 1)

Added:

* `.github/ISSUE_TEMPLATE/bug_report.yml`: "Bug report", `[Bug]: `, label `bug`.
* `.github/ISSUE_TEMPLATE/feature_request.yml`: "Feature request", `[Feature]: `, label `enhancement`.
* `.github/ISSUE_TEMPLATE/issue.yml`: "General issue / task", `[Task]: `, no label.
* `SECURITY.md`: report vulnerabilities privately; never include real keys.

Changed:

* `.github/ISSUE_TEMPLATE/config.yml`: blank issues stay off. The contact links are now "Security
  vulnerability" (private vulnerability reporting) and "Questions and ideas" (this repo's Discussions).
  The upstream Discussions and Wiki links are gone.
* `.github/DEVELOPMENT_WORKFLOW.md`: "development-task template" → the "General issue / task" form.

Removed: the nine markdown templates listed in Phase 0.

Choices:

* Required fields. Bug report: what happened, what you expected, steps, trading mode, version, and the
  redaction checkbox. Feature request: problem and proposed solution. Task: summary. Everything else
  is optional; GitHub shows "None" in an optional dropdown.
* The bug report's secrets warning is a markdown block, at the top and again above the logs field. It
  names Settings → Paths ("Log folder", `app/pt_hub.py` `_user_folder_rows`). The other two forms have a
  one-line reminder.
* Option text is capitalised (`Hub GUI`, `Trainer/thinker`, `Tech debt`). The area list is identical in
  all three forms.
* The version field asks for a commit hash or download date: the repo has no tags and the app shows
  no version number.
* `"Yes"` and `"No"` are quoted so YAML 1.1 parsers don't read them as booleans.

## Validation (commit 2)

`docs/dev/check_issue_forms.py` parses every `.yml` in `.github/ISSUE_TEMPLATE` with PyYAML and checks
it against GitHub's issue-form rules: top-level `name`, `description` and `body`; valid element types
and attributes; a unique id on every element that isn't markdown; non-empty, unique dropdown options.
It also checks this task's own rules: no `.md` templates, the same area list everywhere, and no
auto-label trigger word in a field label or option.

PyYAML is not a project dependency. It was installed in a throwaway venv in the session scratchpad
(Python 3.13.15, PyYAML 6.0.3), not in the repo's `.venv`.

```
> python docs/dev/check_issue_forms.py
OK   bug_report.yml
OK   config.yml
OK   feature_request.yml
OK   issue.yml
OK   area dropdown identical in 3 forms
(exit 0)
```

The checker can fail. Run against broken copies in the scratchpad, it caught all 13 faults put in:
duplicate id, missing id, invalid type, misspelt attribute, duplicate option, empty options, missing
`name`, an unquoted `: ` (parse error), a differing area list, a leftover `.md` template, a trigger word
in a label, an `http://` contact link, and a body with only markdown. Run against `main`'s
`ISSUE_TEMPLATE` folder, it fails on all nine `.md` templates. Black 26.10.0, isort and flake8 (CI's
settings) are clean.

Not checked here: how GitHub renders the forms. GitHub only lists templates from the default branch,
so the "New issue" check is a manual step after merge.

## Owner steps

1. ~~Turn on private vulnerability reporting.~~ Done by the owner after review (`gh api` now returns
   `{"enabled": true}`).
2. ~~Create `task` and `needs-triage` labels.~~ Done; see "Review follow-up".
3. After merge: open "New issue" and confirm exactly three templates (Bug report, Feature request,
   General issue / task), the two contact links, and no blank-issue option.

## Review follow-up (commit 3)

After the review approved the PR:

* Created the labels with the commands from the owner's notes: `task` ("Chore, refactor, docs, tests
  or tech debt", `#1D76DB`) and `needs-triage` ("New issue awaiting review", `#FBCA04`).
* Forms: `needs-triage` added to all three; `task` added to `issue.yml`. Labels are now bug report
  `bug` + `needs-triage`, feature request `enhancement` + `needs-triage`, task `task` + `needs-triage`.
* `python docs/dev/check_issue_forms.py`: all OK, exit 0 (output as above).
* The auto-labeller is **disabled**: `gh workflow list` shows `project-management.yml` as
  `disabled_inactivity` (last run 2026-08-28). The `component-trading` side effect noted in Phase 0
  only applies if it is re-enabled as it is now.
* Follow-up issue #139: label from the Area answer, never set priority or phase from text, and clean
  up the existing priority and phase labels (22 `priority-critical`, 14 issues with two priority labels,
  8 with two phase labels).

## Rules followed

* Own worktree (`..\PowerTraderAI-templates`, branch `chore/issue-templates` from `main` `d815910`).
* Nothing under `app/` changed; no other session's files touched.
* Staged by explicit path only. Three commits: the forms, the checker and this log, then the review
  follow-up.
* Pushed and opened a PR against `main`; not merged.
