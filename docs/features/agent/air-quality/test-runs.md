# Air Quality: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/air-quality.md` or to `air_quality.py` and the `weather.py` helpers it uses. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its judgement is mostly in what it leaves out of the report (the European AQI outside Europe, pollen nobody asked about, past dates it can't answer) and in when to add `--forecast`, so each case gives one fixed question chosen to exercise a rule. The questions state today's date, so a case can be rerun later by changing it.

These are live readings, so the figures change; the cases judge the agent's choices (the place it passed, `--forecast` or not, what it reported and left out), not the air.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "air-quality"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 air_quality.py "..." --json > DIR/01-aq.out 2> DIR/01-aq.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose each flag. Don't end with a question.
```

For a case where the workflow would ask the user something, add: "If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer." Check each run against the saved `.out` / `.err` files (`location`, `admin1`, `us_aqi`, `european_aqi`, the `<plant>_pollen` fields, and with `--forecast` each day's `date` and `hours`).

## Cases

The dates below are for today = Tuesday 2026-10-27. Every case ran on Haiku, the agent's model.

### 1. Current AQI outside Europe

- **Rules:** lead with the US AQI and its category; mention the European AQI only for Europe or when asked; mention pollen only when asked.
- **Question:** `What's the AQI in Delhi right now?`
- **A correct run:** `air_quality.py "Delhi" --json`, no `--forecast`; the report leads with `Delhi: AQI <n> (<category>)`, may call out PM2.5 if it is notably high, and says nothing about the European AQI or pollen.
- **Last checked:** 2026-10-27, **failed**. The figures were right (US AQI 181, Unhealthy, with PM2.5 and PM10 called out), but the report also gave the European AQI (82) and said pollen wasn't reported because it is Europe-only. Rerun after the fix (see below): passed, US AQI 181 (Unhealthy) and the resolved place only.

### 2. A European city

- **Rules:** in Europe, give the European AQI too, side by side with the US AQI and never combined; mention pollen only when asked.
- **Question:** `How's the air quality in Paris today?`
- **A correct run:** `air_quality.py "Paris" --json`; US AQI first, the European AQI beside it with a note that the two scales differ; no pollen.
- **Last checked:** 2026-10-27, passed on the indices (US AQI 34, Good; European AQI 43, not combined), but the report added "the pollen fields are all 0.0" although pollen wasn't asked about. Rerun after the fix (see below): passed: US AQI 34 and European AQI 43 side by side, no pollen.

### 3. Pollen in Europe

- **Rules:** give pollen counts in grains/m³ for the plants above 0, or say all six are at 0; 0 is a real reading in Europe; don't label counts low, moderate or high.
- **Question:** `Is birch pollen high in Berlin right now? I have hay fever.`
- **A correct run:** `air_quality.py "Berlin" --json`; answers the question from the birch count, gives the counts (last time all six at 0) without a low/high band, and may say late October is out of season.
- **Last checked:** 2026-10-27, passed: birch 0 grains/m³, "so it is not high", all six at 0, out of season. Rerun after the fix (see below): passed, pollen still reported when asked.

### 4. Pollen outside Europe

- **Rule:** if every pollen field is `null`, say pollen counts aren't available for that place rather than calling them zero.
- **Question:** `What's the pollen count in Tokyo?`
- **A correct run:** `air_quality.py "Tokyo" --json`; says pollen isn't available for Tokyo (modelled for Europe only), not that it is 0. A one-line US AQI is fine; the European AQI is not.
- **Last checked:** 2026-10-27, passed on pollen ("missing data, not a zero count"), but it also gave the European AQI (62) "for reference only". Rerun after the fix (see below): passed: US AQI 65 and pollen "isn't available here, not that the count is zero", no European AQI.

### 5. "This weekend", partly beyond the forecast

- **Rules:** add `--forecast` for coming days; give each day's worst hour; flag a partly covered day; say when an asked-for day is beyond the last one returned.
- **Question:** `Will the air be bad in Delhi this weekend?`
- **A correct run:** `air_quality.py "Delhi" --forecast --json`; "this weekend" is Saturday 2026-10-31 and Sunday 2026-11-01. Last time the forecast ran 27–31 October, so the report gives Saturday's worst hour (155, Unhealthy), flags it as only 19 hours covered, says Sunday is beyond the forecast, and names the worst day.
- **Last checked:** 2026-10-27, passed.

### 6. Past air quality

- **Rule:** there is no historical air quality; say that isn't available rather than guessing.
- **Question:** `What was the air quality in Beijing last Tuesday?`
- **A correct run:** says air quality for 2026-10-20 isn't available from this tool, without estimating it. Running nothing is best; if it does run the tool, any current reading must be clearly labelled as today's, not last Tuesday's.
- **Last checked:** 2026-10-27, passed on the main rule: it said last Tuesday isn't available and labelled the current reading (US AQI 141) as today's. It ran the tool anyway, and the report again included the European AQI, every pollutant and a pollen line nobody asked for. Rerun after the fix (see below): passed: ran nothing, said 2026-10-20 isn't available, and offered no current reading.

### 7. An unknown place

- **Rule:** report "no location found" plainly and don't retry it.
- **Question:** `What's the air quality in Qwzxplorvania?`
- **A correct run:** one run, exit 1, `No location found matching 'Qwzxplorvania'.` reported as-is; no retry, no guessed place.
- **Last checked:** 2026-10-27, passed. It ended with the Open-Meteo credit line although nothing was fetched; harmless.

### 8. An ambiguous place name

- **Rule:** add a qualifier only when the name is ambiguous and the user gave enough context.
- **Question:** `I live in Maine. How's the air in Portland today?` (with the don't-ask instruction above).
- **A correct run:** `air_quality.py "Portland, Maine" --json`, resolved to Portland, Maine, United States, and the report names the place it used.
- **Last checked:** 2026-10-27, passed on the place (US AQI 30, Good), but the report again gave the European AQI (17) and a pollen line. Rerun after the fix (see below): passed, US AQI 30 only. It explained what it had left out ("European AQI is left out because Portland is not in Europe"); wordy but harmless.

## Found on 2026-10-27

Cases 1, 4, 6 and 8 gave the European AQI for a place outside Europe, and cases 1, 2, 6 and 8 mentioned pollen unasked. The rules are in the agent's "Reporting results" section, but Haiku reads the JSON fields and reports them anyway. Fixed the same day by restructuring the agent's "Reporting results" section: each optional item (European AQI, pollutants, pollen, resolved place) is now a bullet with its condition, a "Leave out" checklist at the end names the two mistakes, and a past-date-only question no longer runs the tool. The agent stays on Haiku.

The reruns were made in the same session as the edit, so they couldn't call the `air-quality` agent itself (agent definitions load at session start). Instead a general-purpose agent on Haiku was told to read `.claude/agents/air-quality.md` and follow it, with the same case prompts. Cases 1, 2, 3, 4, 6 and 8 passed that way; rerun them through the real agent in a new session to confirm.

## Not covered

- A forecast question for Europe with pollen ("pollen forecast for Vienna"); in October every count is 0, so rerun it in spring.
- A transient network failure (retry at most once); it can't be forced from the command line.
