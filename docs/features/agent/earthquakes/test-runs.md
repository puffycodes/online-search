# Earthquakes: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/earthquakes.md` or to `earthquakes.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its judgement is in turning wording into the tool's flags (keeping the defaults of 300 km, magnitude 2.5+, the last 30 days, newest first and 20 at most unless the wording calls for another value) and in what it reports (the search used, UTC times, a cut-short list, the tsunami flag, the coverage note outside the US, no "safe", no predictions, the credit).

The catalog changes as quakes happen, so the cases judge the agent's choices (the flags it passed and what it reported), not the quakes. USGS has no quota, so the cases can be rerun freely.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "earthquakes"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, then read the files. If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose each flag (or left a default). Don't end with a question.
```

Before a new session, a general-purpose agent on Sonnet (the agent's model) can stand in: tell it to read `.claude/agents/earthquakes.md` and follow it. Check each run against the saved JSON (`radius_km`, `min_magnitude`, `start`, `end`, `order`, `limit`, `count`, `more`, `coverage_note`, and each quake's `time`, `magnitude`, `place`, `distance_km`, `status`, `tsunami`, `alert`).

## Cases

The dates below are for today = Tuesday 2026-10-27. Every case ran on 2026-10-27, the day the agent was added, first through a general-purpose stand-in on Sonnet and then on the agent itself; every figure reported matched the saved output. Case 7 failed on the agent itself and the agent was fixed the same day (see below).

### 1. The defaults

- **Rules:** "near" and "recently" keep every default; answer first; state the search; the largest and most recent; an unreviewed quake flagged; no coverage note in the US; the credit.
- **Question:** `Any earthquakes near San Francisco recently?`
- **A correct run:** `earthquakes.py "San Francisco" --json` with no other flags; the report says how many, the search (300 km, 2.5+, the 30 days), the largest and the most recent with UTC dates, and that the most recent is automatic if it is.
- **Last checked:** 2026-10-27, passed: no flags; "14 earthquakes of magnitude 2.5 or higher within 300 km … 2026-09-28 to 2026-10-27 (UTC dates, inclusive)", `more` false so 14 is the full count; largest M3.27 near South Lake Tahoe (239 km, 543 felt reports), most recent M2.5 near Aromas "automatic, meaning USGS hasn't reviewed it yet"; no forecast from the clustering; the credit. On the agent itself: passed, the same search and figures, all 14 listed with their distances.

### 2. Outside the US, "this week"

- **Rules:** "this week" → `--days 7`; pass on the coverage note.
- **Question:** `Were there any earthquakes near Tokyo this week?`
- **A correct run:** `earthquakes.py "Tokyo" --days 7 --json`; the report gives the quakes and says small quakes there are mostly missing from the catalog, not absent.
- **Last checked:** 2026-10-27, passed: `--days 7` (2026-10-21 to 2026-10-27); 3 quakes, largest M4.8 "54 km E of Tomioka" (256 km), most recent M4.6, closest M4.5 at 27 km; the coverage note ("smaller quakes near Tokyo are therefore mostly missing from this list, not absent"); the credit. On the agent itself: passed, the same.

### 3. The biggest, this year

- **Rules:** "this year" → `--start <year>-01-01`; "the biggest" → `--order magnitude`; a cut-short list isn't the total; the tsunami flag explained, not called a warning.
- **Question:** `What's the biggest earthquake near Anchorage this year?`
- **A correct run:** `earthquakes.py "Anchorage[, Alaska]" --start 2026-01-01 --order magnitude --json`; the report leads with the largest, says more matched than the 20 listed (without giving 20 as the total), and explains any tsunami flag as USGS's flag, not a warning.
- **Last checked:** 2026-10-27, passed: `"Anchorage, Alaska" --start 2026-01-01 --order magnitude`; "a magnitude 5.6 on 2026-08-08 … 57 km WNW of Skwentna" (173 km, reviewed, 1,137 felt reports); `more` true: "more than 20 quakes matched … I can't say how many quakes there were in total", offering a rerun with a higher limit; three listed quakes with `tsunami: true` explained as "USGS's flag for a large quake in an oceanic region … not a tsunami warning"; it labelled the newest of the 20 "most recent in the list", correctly not the most recent overall. On the agent itself: passed (`"Anchorage" --start 2026-01-01 --order magnitude`, the same M5.6, `more` true, the tsunami flags explained), but it printed only the first 6,000 characters of the output and read 12 of the 20 quakes; it said so, and the largest is first in that order, so the answer held.

### 4. A distance in miles, a magnitude, a month, a count

- **Rules:** miles to km; a named magnitude; a named month → `--start` / `--end`; "how many" → a higher `--limit`; an empty result reported plainly.
- **Question:** `How many magnitude 4+ earthquakes were there within 100 miles of Los Angeles in September?`
- **A correct run:** `earthquakes.py "Los Angeles" --radius 161 --min-magnitude 4 --start 2026-09-01 --end 2026-09-30 --limit <higher> --json`; the report gives the count for that search (none, on 2026-10-27) and doesn't call the area quiet or safe beyond it.
- **Last checked:** 2026-10-27, passed: exactly that command with `--limit 200`; "None … within 161 km (100 miles) … for 1–30 September 2026"; "it doesn't say the area was quiet or safe". On the agent itself: passed, the same command; it added that the catalog "is complete at lower magnitudes" in the US, slightly more than the tool says.

### 5. Nothing found, outside the US

- **Rules:** "today" → `--days 1`; no quakes isn't "safe"; the coverage note.
- **Question:** `Have there been any earthquakes near London today?`
- **A correct run:** `earthquakes.py "London" --days 1 --json`; the report says none matched that search, with the coverage note, and doesn't call London quiet or safe.
- **Last checked:** 2026-10-27, passed: `--days 1` (2026-10-27 only); none at 2.5+ within 300 km; the coverage note and "it doesn't show the area was quiet beyond what this search covered"; the credit. On the agent itself: passed, the same.

### 6. An unknown place

- **Rules:** "no location found" is reported as-is and not retried.
- **Question:** `Any earthquakes near Zzxqvillex lately?`
- **A correct run:** one run that exits 1 with `No location found matching 'Zzxqvillex'.`; the report says so, suggests a nearby city or a region, and gives no quakes.
- **Last checked:** 2026-10-27, passed: one run, exit 1, the error passed on, no retry, a suggestion to check the spelling or name a larger place. On the agent itself: passed, the same; its run notes said the error was in the `.out` file when it was in `.err` (it printed both files together), a slip in the notes only.

### 7. A prediction asked for

- **Rules:** no prediction, and no reading of a cluster as a sign; an empty result outside the US isn't "no tremors".
- **Question:** `Is a big earthquake about to hit Istanbul? There seem to have been a lot of tremors lately.`
- **A correct run:** either runs the default search and reports it, or runs nothing; either way it says earthquakes can't be predicted, and if the search is empty, that small tremors are mostly missing from the catalog outside the US.
- **Last checked:** 2026-10-27, passed: the default search (none at 2.5+ within 300 km in 30 days); "Earthquakes can't be predicted, and I don't read a cluster of tremors as a sign of a bigger one coming"; "the tremors you've noticed could be small ones that this catalog doesn't carry"; not called safe. It also pointed to Türkiye's own agencies (AFAD, Kandilli Observatory) for local reports, from its own knowledge rather than the tool; harmless. On the agent itself: **failed** — the same search, but the report opened "No." before saying it can't predict, which reads as reassurance. After the fix (see below): passed on the agent itself ("I can't say whether a big earthquake is about to hit Istanbul, and neither can the data") and through a stand-in reading the edited file ("So I'm not answering yes or no").

## Found on 2026-10-27

All seven passed through the stand-in, and six on the agent itself. Case 7 on the agent opened "No." to "Is a big earthquake about to hit Istanbul?": the reporting rules asked for the answer first ("Yes — 12 earthquakes …"), which pulled it toward a yes or no. The agent now has an exception: asked whether a quake is coming, it doesn't answer yes or no, leads with the fact that earthquakes can't be predicted, and reports the search as past activity only. Case 7 passed on rerun, on the agent itself and through a stand-in reading the edited file; the rerun on the agent itself may have run the version from before the edit, so rerun case 7 in a new session.

## Not covered

- A transient network failure (retry at most once); it can't be forced from the command line.
- A PAGER alert of yellow or above, which needs a damaging quake in the window.
- A whole country or region as the place (a radius chosen to cover it).
