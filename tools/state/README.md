Durable state (committed with each published post):

- `seen.json` tracks ingested URLs.
- `published.json` records live posts.

Per-run scratch state (regenerated and never committed):

- `inbox.json` holds new feed items.
- `todays-brief.json` stores the selected assignment.
- `draft.json` stores model output.
- `verify-report.json` stores the accuracy-gate result.
- `logs/` contains pipeline logs.
- `held/` contains artifacts from posts held after verification failures.
