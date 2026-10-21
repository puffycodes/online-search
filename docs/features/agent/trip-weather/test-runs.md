# Trip Weather: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/trip-weather.md` or to `trip_weather.py` and the weather modules it uses. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its main judgement is turning the user's words into dates and keeping forecast and typical weather apart, so each case gives one fixed question chosen to exercise a rule. The questions state today's date, so a case can be rerun later by changing it.

These are live forecasts and archives, so the figures change; the cases judge the agent's choices (dates, flags, what it ran or didn't, how it labelled typical weather and air quality), not the weather.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "trip-weather"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 trip_weather.py "..." ... --json > DIR/01-trip.out 2> DIR/01-trip.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying how you turned the user's wording into dates and why you chose each flag. Don't end with a question.
```

For a case where the workflow would ask the user something, add: "If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer." Check each run against the saved `.out` files (`start_date`, `end_date`, `typical_years`, each day's `source`, `air`, `notes`).

## Cases

The dates below are for today = Wednesday 2026-10-21.

### 1. "Next week"

- **Rule:** turn relative dates into `--start` / `--end` ("next week" → next Monday to Sunday) and say which dates were used.
- **Question:** `What's the weather going to be like in Lisbon next week?`
- **A correct run:** `trip_weather.py "Lisbon" --start 2026-10-26 --end 2026-11-01`; all seven days are forecast; the report states the dates, says there is no air-quality forecast that far ahead, and gives the forecast with UV and sun times.
- **Found on 2026-10-21:** the report couldn't give the wind's unit, since the agent's field list didn't say. It now says km/h.
- **Last checked:** 2026-10-21, passed.

### 2. Forecast and typical weather in one trip

- **Rule:** keep typical days visibly separate, labelled "typical weather for those dates over <years>, not a forecast", and never present them as a prediction.
- **Question:** `I'm going to Kyoto from 3 to 10 November. What weather should I expect?`
- **A correct run:** one run from 2026-11-03 to 2026-11-10; a forecast table for the first days and a separate, labelled table of typical days (with ranges and wet years); air quality said to be beyond its forecast.
- **Last checked:** 2026-10-21, passed.

### 3. A stay over 31 days

- **Rule:** "For a longer stay, ask which part matters most, or run it in 31-day pieces."
- **Question:** `I'll be staying in Cape Town for December and January. What will the weather be like?` (with the don't-ask instruction above).
- **A correct run:** says what it would have asked, then runs two pieces within the limit (last time one per month) and explains why the two pieces' typical years differ (2021–2025 for December, 2022–2026 for January). Everything is labelled typical.
- **Last checked:** 2026-10-21, passed.

### 4. Past dates

- **Rule:** "For past dates, use the `weather-history` agent instead."
- **Question:** `What was the weather like in Rome last week during my trip?`
- **A correct run:** runs nothing, gives no figures, and points to the `weather-history` agent with the dates worked out (2026-10-12 to 2026-10-18).
- **Found on 2026-10-21:** the agent added the Open-Meteo credit line although nothing was fetched. Harmless, but the credit rule now says it's for reports with figures from the tool.
- **Last checked:** 2026-10-21, passed.

### 5. Packing advice and air quality

- **Rules:** advice only from the figures; air quality as each day's worst hour; never combine the US and European AQI; say pollen is Europe-only.
- **Question:** `I fly to Delhi tomorrow for three days. What should I pack, and is the air OK?`
- **A correct run:** 2026-10-22 to 2026-10-24, all forecast with air quality; the report answers "is the air OK" plainly (last time US AQI 170–187, Unhealthy), keeps the European AQI separate, and grounds every packing item in a figure.
- **Last checked:** 2026-10-21, passed.

### 6. Fahrenheit, all typical

- **Rule:** `--unit fahrenheit` only when asked or clearly expected; a trip beyond the forecast is all typical.
- **Question:** `We're taking the kids to Orlando from December 20 to 27 — what kind of temperatures in °F should we expect?`
- **A correct run:** `--unit fahrenheit`, eight typical days labelled as such, a cold-snap caveat from the ranges, and advice to re-check once the dates are within the forecast.
- **Found on 2026-10-21:** the agent noticed that the typical days' sun times were an hour late (sunset 18:33 instead of about 17:33). The cause was Open-Meteo applying the place's offset *today* (EDT) to every date, including December (EST). It affected `weather_history.py` and forecast days after a daylight-saving change too. Fixed the same day in `weather.local_daily()`, which converts sunrise and sunset to each date's own offset; the agent's one-hour correction is no longer needed.
- **Last checked:** 2026-10-21, passed.

## Not covered

- An ambiguous place name (e.g. "Springfield"), where the agent should add a qualifier from context.
- A trip partly within the air-quality forecast (only the first days have AQI); covered in the script's tests, not yet in a live run.
