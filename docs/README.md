# docs

Plain-English explanations of the analysis tools in this repository — written for
someone who knows a little about stocks but not the underlying maths.

| File | Covers | Module |
|---|---|---|
| [indicators.md](indicators.md) | Price indicators: moving averages, price-vs-average, moving-average crossovers and their "flips", rebasing a series to a chosen day, and the up/down/flat trend classifier | [`../indicators.py`](../indicators.py) |
| [valuations.md](valuations.md) | Intrinsic-value methods: discounted cash flow, reverse DCF, the Gordon growth / dividend model, and price & enterprise multiples | [`../valuation.py`](../valuation.py) |

The project [`README.md`](../README.md) has the precise, function-by-function API
reference. These pages are the friendly version: what each tool tells you, how to
read the result, and what to watch out for.

**A note on all of them:** the indicators *describe* what prices have already
done — they do not predict. The valuation tools *estimate* what a business might
be worth, but every estimate depends on assumptions you choose, and the answer
moves a lot when the assumptions move. Nothing here is investment advice.

## Agent feature specs

[`features/agent/`](features/agent/) holds one `features.md` per Claude Code subagent
in [`../.claude/agents/`](../.claude/agents/), in a folder named after the agent
(e.g. [`features/agent/weather/features.md`](features/agent/weather/features.md)
for `.claude/agents/weather.md`). Each spec states which script(s) the agent must
use and what it does, in the same Requirement / Actions format as the web apps'
specs in `app/*/docs/features.md`. They live here rather than in `.claude/agents/`
because Claude Code loads every `.md` file in that folder as an agent.
