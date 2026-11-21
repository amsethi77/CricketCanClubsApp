# CricketClubApp QA Testcases

This file captures the local QA automation plan for the current app behavior.
The source of truth for product rules is [`README.md`](README.md).

The goal is to keep the QA suite traceable back to the requirement log in the README.
The automated suite covers the main product surfaces end-to-end on isolated local data:

- authentication and RBAC
- clubs and player snapshot resolution
- season fixtures and availability
- live scorebook updates
- player profile and chat
- registration and admin center access
- non-functional health, latency, and page-render smoke tests

## Test Data

- `TestClub`
- `player1` / `1111111111`
- `captain1` / `2222222222`
- `clubadmin1` / `3333333333`
- `Amit S` / `14164508695`

## Requirement Coverage Map

| README areas | Coverage focus | Automated test IDs |
|---|---|---|
| Core product, identity, auth, club-first landing | Signed-in identity, visible clubs, session handling, registration | U01-U04, U08-U09, F03-F04, F11, N04 |
| Clubs, dashboard, widget launcher, current season, player snapshot | Club scoping, current season selection, canonical member resolution, widget-specific dashboard pages | U05-U07, F01-F02, N01, N03, N05, F17 |
| Season Fixtures, scoring, and availability | Season list, fixture CRUD, live scorebook setup, text/voice scoring, past-fixture lock, availability save | U05, F05-F08, F10, N05 |
| Player profile, rankings, chat, history, and LLM service layer | Cross-club profile data, clubs dedupe, AI/RAG question answering, prompt registry, direct inference, predictive analysis | U06, F12, F13, N03, N06, N07 |
| Admin Center and scorecard review | Superadmin-only access and scorebook / archive controls | U09, F09, F07 |
| Sign-in and landing-page widgets | Leader widgets, public leaderboard stats, live LLM badge state beside Assistant, and chat cache reset | F03, N04, N06, F15 |
| Non-functional checks | Page render, health, response latency | N01-N05 |

## Unit Testcases

| ID | Area | Preconditions | Steps | Expected |
|---|---|---|---|---|
| U01 | Auth scoping | Signed in as `player1` | Call `/api/auth/me` | Auth payload returns `viewer_member_name = player1` and only `TestClub` is visible. |
| U02 | Auth scoping | Signed in as `Amit S` | Call `/api/auth/me` | Auth payload returns canonical member identity and only clubs linked to Amit S. |
| U03 | Club membership | Loaded player profile data | Resolve club memberships for Amit S | Duplicate club memberships are removed before display. |
| U04 | Registration options | Public page load | Call `/api/auth/options` | Superadmin is not exposed and public options include non-superadmin roles. |
| U05 | Season setup | Signed in as `captain1` | Call `/api/season-setup/data?club_id=club-testclub` | Current year is present and fixtures are scoped to `TestClub`. |
| U06 | Player profile data | Signed in as `Amit S` | Call `/api/player/profile-data` | Profile payload includes contact, role, summary, year stats, club stats, and deduped club history. |
| U07 | Dashboard payload | Signed in as `player1` | Call `/api/dashboard?focus_club_id=club-testclub&selected_season_year=2026` | Dashboard stays on the selected year and visible clubs remain club-scoped. |
| U08 | New club registration | No session required | Register a player with a new club name, city, and country | New club is created and the registering user becomes club admin. |
| U09 | Admin access | Signed in as captain vs superadmin | Call `/admin-center` | Captains are denied; superadmin can open the Admin Center. |
| U10 | Chat scoping | Signed in as a player | Call `/api/chat` with `What is <player name> total score across all clubs in 2025?` | Chat uses the global club dataset and returns the 2025 total, not the current club-only total. |
| U11 | Chat search stats | Signed in as a player | Call `/api/chat` with `Search <player name> and show their stats` | Chat returns a player stats summary across all clubs. |
| U12 | Chat scorecard mentions | Signed in as a player | Call `/api/chat` with `Which scorecards mention <player name> in 2025?` | Chat lists the stored scorecards that mention that player in 2025. |
| U13 | Chat forecast | Signed in as a player | Call `/api/chat` with `Predict <club name> batting, bowling, and fielding outlook for 2026 and 2027` | Chat returns a grounded forecast using the local LLM and stored year-by-year trends. |
| U14 | LLM service layer | Signed in as a player | Call `/api/llm/status`, `/api/llm/prompts`, `/api/llm/documents`, and `/api/llm/infer` | The API exposes the prompt registry, indexed corpus, and direct inference path backed by the prompt library. |
| U15 | Captain recommendation | Signed in as a player | Call `/api/chat` with `Who should be the captain of Coca Cola team in 2026?` | Chat returns a provisional club-specific captain recommendation instead of an unassigned dead-end. |

## Functional Testcases

| ID | Area | Preconditions | Steps | Expected |
|---|---|---|---|---|
| F01 | Clubs snapshot | Signed in as `Amit S` | Open `/clubs` | Player Snapshot resolves to `Amit Sethi`, not `Amit G`. |
| F02 | Clubs snapshot | Signed in as `player1` | Open `/clubs` | Player Snapshot resolves to `player1`. |
| F03 | Sign-in page | Any browser session | Open `/signin` | The page renders the login form and the three leader widgets without a script crash. |
| F17 | Dashboard widgets | Signed in as `player1` | Open `/dashboard` and then `/dashboard/widgets/scoring` | The dashboard opens as an overview hub with core module navigation, and the widget route shows only the selected widget section. |
| F04 | Register page | Any browser session | Open `/register` | The page renders the registration form successfully. |
| F05 | Fixture create | Signed in as `captain1` | Create a future fixture for `TestClub` via Season Fixtures | Fixture is created and returned in the season fixture list. |
| F06 | Fixture update | Signed in as `clubadmin1` | Edit the created future fixture | Fixture is updated successfully. |
| F07 | Live scorebook | Signed in as `captain1` | Set up an innings, add a ball, and save a commentary transcript on the created fixture | The fixture scorebook persists the setup, ball entry, and text/voice scoring notes. |
| F08 | Player availability | Signed in as `player1` | Mark availability for the created fixture | Availability is stored against the selected club and fixture. |
| F09 | Admin center RBAC | Signed in as captain then superadmin | Open `/admin-center` | Captain gets forbidden; superadmin gets the review page. |
| F10 | Past fixture lock | Signed in as `captain1` | Attempt to edit a fixture whose date is in the past | API returns `Past fixtures cannot be edited.` |
| F11 | Sign out | Signed in as any user | Call sign out, then `/api/auth/me` | Session is invalidated and auth lookup returns unauthorized. |
| F12 | Chat / RAG | Any browser session | Ask `What is <player name> full name?` through `/api/chat` | Chat returns a grounded answer and preserves the session id. |
| F13 | Chat forecast | Any browser session | Ask `Forecast <player name> runs and batting average for the next season` through `/api/chat` | Chat returns a local-LLM forecast grounded in year and club trends. |
| F14 | LLM inference API | Any browser session | Call `/api/llm/infer` with a prompt name and template args | The LLM service returns a structured answer, mode, prompt name, and source label. |
| F15 | Clear chat | Any browser session | Click `Clear chat` in the Assistant header | The browser conversation state and cached LLM answers are cleared, and the Assistant resets to a fresh prompt. |
| F16 | Captain recommendation | Any browser session | Ask `Who should be the captain of Coca Cola team in 2026?` through `/api/chat` | Chat returns a grounded provisional captain recommendation for the requested club. |
| F18 | Register | New mobile number | Register on `/register` | "You're registered" box, then `/signin` with the number filled in; not signed in. Same number again -> "already exists" error. |
| F19 | Rename on one team | A card with "Rafa" on both teams | In the editor rename Rafa -> Rafael on one team | Only that team's batting / bowling / How out change. |
| F20 | Scorecard PDF | A published scorecard (uploaded and live) | Tap "⬇️ Download PDF scorecard" | A PDF with innings, (c)/(vc)/(wk), extras, bowlers, fall of wickets, info. |
| F21 | Photo stored compressed | Signed in, a 5-9 MB phone photo | Upload it | Stored file in `app/uploads/` is under 450 KB; the AI read the full-size copy; uploading the same photo again is refused. |
| F22 | No duplicate copies | Copy an existing photo into `app/uploads/` under a new name, restart | Open Admin Center duplicates | The copy is deleted and listed as a duplicate; nothing new in `app/duplicates/`. |
| F23 | Compress old photos | Superadmin, photos over 450 KB | Scorecard Tools -> "Compress N photos" | All photos under ~450 KB; scorecards still show their photos. |
| F24 | Backups | Superadmin | `/admin/backups` -> Back up now | A new `.db.gz`; "Last try" shows it was made; free space shown. |
| F25 | My availability order | Player with several matches | Open `/player-availability` | Newest match date on top. |
| F26 | Costs / AI accuracy off the site | Superadmin | Open Admin Center; call `/api/admin/costs` | No Costs / AI accuracy tabs; the API answers 404. `python scripts\costs_and_accuracy.py` prints the report. |
| F27 | Start like Azure | Project folder | `python -m uvicorn app.main:app --port 8000` | App starts; /api/health 200 (the pipeline checks this too). |
| F28 | Captains' wins and losses | Heartlake, season 2026 | Stats page -> captains table | Every match counted (P = W + L + T/NR + NA); usual captains who played (Steve, Checkley) shown with *; NA for cards without a result, not in Win %; two matches on the same day both counted; a fixture and its uploaded card counted once. |
| F29 | Scorecard on a played match | Player who played past matches | Open `/player-availability` | Each played match with a published / live-scored card has "📋 View scorecard"; it opens that match's scorecard. |
| F30 | Passwords stored safely | Fresh registration; an old account with a SHA-256 value | Register; restart; sign in with each | New value starts `pbkdf2_sha256$600000$`; old one is wrapped at start-up and becomes `pbkdf2_sha256$` after sign-in; both sign in with their password; no 64-character plain hashes left. |
| F31 | Upload without the AI reader | No Gemini key, or a Free user whose AI try is used | Upload a scorecard photo | The upload is read by the local reader (or left for typing in) and ends as "Pending review" / "Needs admin review" - never "couldn't be read: cannot be re-extracted". |
| F32 | Name tags only | A scorecard with captain / vice-captain / keeper | Open the scorecard, the live match page and Admin Center -> People & roles | Names show (c), (vc), (wk) / (c & wk) only - no bat, ball, lightning or glove icon. |
| F33 | Quick captains Save | An uploaded scorecard, signed in as captain / admin | Pick a captain and man of the match, tap Save | Button shows "Saving…", done in about a second (was several); (c) appears by the name; the Stats captains table counts it. |
| F34 | Captain is not vice-captain | Scorecard pickers (uploaded and live) | Pick X as captain, then open vice-captain; try to save X as both | X is greyed out as vice-captain; Save shows "the captain and the vice-captain can't be the same player"; the API answers 400. Captain + keeper the same is allowed. |
| F35 | Admin Center Overview per club | Superadmin; pick each club in the Admin Center club list | Open Overview, then Club Maintenance | Members = Club roster count; Matches played = the club's games in all seasons (Amit CC: 15 members, 1 match, 1 won); Fixtures / Uploaded scorecards / Top Batter are the picked club's for the season (not Heartlake's); a club admin can't load another club's numbers. |
| F36 | Live only after the 1st ball, Completed after both innings | A club fixture dated today; signed in as its scorer | 1) Set its status to Live, no ball; 2) pick openers; 3) score 1 ball; 4) finish the 1st innings; 5) finish the 2nd innings; check Home, `/live`, Fixtures and `/live/<id>` each time | 1-2: in "Coming up", shown Scheduled / UPCOMING, not "In progress"; 3-4: in "Live now", LIVE (innings break still live); 5: in "Recent results", Completed / RESULT with the result. Undo every ball -> back to Scheduled. The match edit form still shows the saved status. |
| F37 | Fast fixtures and scorecards lists | Any data; open `/fixtures` and `/scorecards` twice | Then change something (approve a card, edit a fixture, pick a man of the match on a live-scored match) and open them again | The second visit is quick (well under a second); after the change the new data shows at once, never an old copy. |

## Non-Functional Testcases

| ID | Area | Preconditions | Steps | Expected |
|---|---|---|---|---|
| N01 | Performance | Signed in as `player1` | Fetch `/api/dashboard` for the current club | Response completes within the local latency budget. |
| N02 | Availability | App running locally | Fetch `/api/health` | Health endpoint responds quickly and returns `ok`. |
| N03 | Stability | Fresh browser session | Reload `/signin`, `/clubs`, and `/season-setup` | Pages render without script crashes or stale fallback player selection. |
| N04 | Leader widget latency | Any browser session | Fetch `/api/public/signin-stats` | Public leader stats are returned quickly and contain batting, bowling, and club lists. |
| N05 | Season setup responsiveness | Signed in as `captain1` | Fetch `/api/season-setup/data?club_id=club-testclub` | Season year list is populated and the response stays fast. |
| N06 | Assistant status chip | Any browser session | Open `/dashboard` and inspect the Assistant header | The status chip beside Assistant shows a colored dot and text for solid green `Online`, blinking green `Thinking`, blinking red `Connecting`, and solid red `Offline`. |
| N07 | LLM safety filter | Any browser session | Ask the chat a profanity-heavy question | The response is moderated and stays cricket-focused and respectful. |
| N08 | Live scoring console | Signed in with an active match selected | Open the scoring panel and inspect the live scoreboard area | The scoring panel shows a scoreboard-style header, live ball chips, and cleaner batting and bowling tables instead of a plain form-only layout. |
| N09 | Quick scoring shortcuts | Signed in with an active match selected | Click a quick action like `4` or `Wicket`, then use `Save & next ball` | The scorer pre-fills the delivery, saves it, and advances the ball number for the next entry. |
| N10 | Mobile parity docs | Any developer session | Open `README.md`, `ios/README.md`, and `android/README.md` | The three app surfaces are documented as a parity set, with shared feature expectations called out explicitly. |

## Automation

Run the local QA suite with:

```bash
python3 -m unittest -v tests.test_local_qa
```

Seed the live local app with the shared `TestClub` scenario:

```bash
python3 scripts/seed_testclub_main.py
```

The seeded QA data lives in the normal local runtime on `http://127.0.0.1:8090`
and writes to the standard `app/data` database and cache files.
It includes a completed two-innings scorebook fixture plus a separate uploaded-image
scorecard fixture so the main app can show innings 1, innings 2, archives, and standings
without any extra QA port or extra database.

The match center also covers text and voice scoring:

- text scoring notes saved from the form
- browser mic transcription saved as voice scoring notes
- commentary entries persisted with each match alongside the scorebook

The test suite still uses isolated copies of the SQLite database and cache files
so it does not mutate the real local runtime data.
