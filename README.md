# CricketClubApp

Local-first CricketClubApp product with a web app plus matching iOS and Android app surfaces. The three surfaces are kept in lockstep so the same cricket workflows are available everywhere.

## What it includes

- Team member profiles with age, role, picture URL, phone, email, and notes
- Season schedule with visiting teams
- Match setup with captain, venue, toss, scorer, and status
- Player availability tracking by match
- Live scoring and scorecard updates
- Player performance tracking for runs, wickets, catches, fours, and sixes
- Text and voice scoring with transcript capture per match
- WhatsApp launch link for match coordination
- Free AI-style Q&A over the stored club data
- Scorecard image upload plus archive-review flow for offline score recovery
- Ball-by-ball innings scorebooks with 11 batters and 11 bowlers per innings
- Local viewer registration with mobile or email
- Primary-club selection and club-first landing experience
- Club search, player search, quick stats, and followed-player watchlist
- Landing-page highlights for recent scorecards, matches, and club stats

## Canonical Product Rules

These rules are the source of truth for the current implementation. If older log items conflict with them, these rules win.

- The signed-in identity must come from the backend auth session and `app_users` row, not from the first matching player shown in the UI.
- `member_id` is the canonical player link for the logged-in account. Display names, short names, and aliases are presentation-only labels.
- The dashboard, clubs page, season fixtures page, and availability page must all use the logged-in user and active club from the backend payload first.
- The clubs page may show only clubs linked to the signed-in identity. It must not show every club by default after login.
- The dashboard player snapshot must default to the authenticated member linked to the account. It must not fall back to another roster member just because that member appears earlier in the list.
- If a player belongs to multiple clubs, the player profile may show cross-club career history, but each club dashboard remains club-local.
- Sign out must invalidate the server session and clear the browser auth state.
- Success and loading chatter should stay quiet in the UI unless it is needed for a real error or actionable confirmation.

## Prompt And Requirement Log

This section captures the user requirements in the order they were given and refined during the build.

### Original feature scope

1. Create a cricket website app for CricketClubApp Club.
2. Add team members and profile creation with picture, age, and related details.
3. Add scoring.
4. Add visiting teams.
5. Add scorecards.
6. Add schedule and player availability tracking.
7. Add WhatsApp integration.
8. Add free LLM integration for open questions over stored data.
9. Extract scores from previous-year scorecard images.
10. Provide a feature to score matches.
11. Add live text and voice scoring, speech-to-text, and persistence per match.
12. If scoring cannot be done online, allow scorecard image upload, extract the score, create the online scorecard, and update player scores.
13. Use SQLite for persistence and JSON/cache for fast retrieval.
14. Keep the website UI easy to use and trendy.
15. Use player mobile number for uniqueness.

### Archive, data, and identity refinements

16. Process files from the uploads directory automatically.
17. Ignore duplicate uploads and move duplicates into a duplicate-review folder together with the original file.
18. Add players found in reviewed CricketClubApp scorecards into the CricketClubApp player list and into the database.
19. Store players against their team name in the system.
20. Support player full names and aliases and let the system detect them.
21. Do not hard-code aliases or full-name mappings in code; persist them in the database.
22. Accept user questions by alias or short name, but answer using full names.
23. Treat `Amit S` and `Amit Sethi` as the same player.
24. Treat `Amit`, `Amit G`, and `Amit Gaba` as the same player.
25. Keep `Amit S` and `Amit G` as different players.
26. `John` from CricketClubApp can also play for `Coca Cola XI`.
27. `Vinay` in the Coca Cola team is the same person as `Vinny`.
28. `Imran XI` is Imran's primary team and `CricketClubApp` is secondary.
29. Credit Imran's catches against CricketClubApp when he played for another team.

### Season and archive rules

30. Availability belongs to the `2026` season only.
31. The currently loaded historical scorecards belong to `2025` or earlier, not to the 2026 season.
32. Do not apply old scorecards onto future 2026 fixtures.
33. Retrieve archive date from the scorecard itself when possible; otherwise use image metadata.
34. Allow retrieval of old scorecards by exact date, by player, or by year.
35. Treat all currently loaded uploaded scorecards as `2025 Season` unless an explicit historical year is provided.
36. Keep the top-level site season anchored to the running CricketClubApp season, not to a historical club season.

### Player stats, rankings, and chat behavior

37. Show individual player scores clearly on the site.
38. Add a player profile page with match-by-match history.
39. Add a teams page and team-level traversal links.
40. Calculate batting rankings using total runs, matches, average runs per match, and strike rate.
41. Calculate bowling rankings using wickets taken.
42. Calculate fielding rankings using catches and related fielding stats.
43. Show rankings year-wise and allow year selection.
44. If a player belongs to multiple clubs or teams, show all clubs and club-specific rankings on the profile.
45. Unless a club or team is explicitly requested, answer player questions across all clubs and teams.
46. Support ranking-style questions such as top batter, most wickets, most catches, reliability, consistency, and top 5 batters.
47. Support profile questions such as age, phone, batting order, best batting order, best score, and best-score opponent.
48. Maintain chat session context so follow-up questions like `what is his age?` still refer to the prior player.
49. Use a grounded local RAG-style flow for open questions over persisted data.

### Batting average and scoring rules

50. Batting average should be `total runs / times out` when outs are known.
51. If outs are not available, batting average should fall back to `total runs / batting innings`.
52. `Did not bat` innings are excluded from batting-average calculations.
53. A reviewed `not out` innings should increase batting average correctly.
54. Best-score answers should use the highest stored score from the persisted records and keep the player context on follow-up questions.

### Live scoring and offline recovery

55. Multiple-match live scoring and offline recovery should support 11 batters and 11 bowlers per innings.
56. Scoring should be ball by ball.
57. Ball-by-ball capture should respect the overs limit for the innings.
58. The persisted scorebook should roll up into scorecards and player performances.
59. Update `README.md` with every prompt provided so requirements are not lost.
60. Registration should work with mobile number or email.
61. Initiate the website or app by selecting the club or searching the user's primary club.
62. Once the primary club or selected club is chosen, it should become the main focus.
63. Support searching a club.
64. Support searching a player and showing the player's stats.
65. Allow following a player.
66. The website main landing page should show upcoming events, matches, and club stats.
67. Convert the experience into a multi-page application instead of relying only on the single-page dashboard.
68. Add separate pages for registration and sign-in.
69. After sign-in, let the user select a club, defaulting to the primary club while still allowing other clubs to be selected.
70. Let club administrators set up schedules for new seasons such as 2026 and 2027.
71. Let players provide their own availability after login.
72. Make season setup year-aware so multiple future seasons can coexist without replacing the current running season.
73. Keep player-availability updates focused on the selected club and its active season.
74. Commit the codebase to GitHub before deployment.
75. Create an Azure deployment plan for a lightweight App Service release in Subscription 1, Canada Central using GitHub Actions.
76. Do not lose runtime data; keep a checked-in JSON snapshot / recovery export strategy alongside the live database, uploads, and duplicate-review files.
77. Add a `Male` / `Female` gender field to player profiles and make it persist in the database.
78. Add a separate Admin Center with its own access rules for club administrators and superadmins.
79. Keep uploaded scorecards in review until an admin reviews, edits, and approves them.
80. Prevent players from editing other players' stats; players may update only their own profile and availability.
81. Show scorecard status on the dashboard as `Pending review` or `Approved`, with approved scorecards moving into the database.
82. Keep club dashboards club-local so rankings, squad, scorecards, fixtures, and match info only reflect the selected club.
83. Keep player profiles cross-club so a player can show memberships, rankings, and match history across all clubs.
84. Make the selected season drive the dashboard view, with `2026` as the default and historical seasons available from a dropdown.
85. Disable live scheduling, scoring, availability, and commentary controls for historical seasons such as `2024` and `2025`.
86. Use a modern Tailwind CSS + Node-based visual refresh for the web app.
87. Make dashboard availability updates save reliably for the selected club and match.
88. Ensure the dashboard and multipage flows always send the signed-in auth token with requests.
89. Show a player snapshot immediately after login, before or alongside club selection.
90. Split player snapshot stats into year-wise and club-wise tables.
91. Cache player and club summary breakdowns in SQLite tables for fast reads.
92. Use cricket-style milestone bands for summary stats: `25+`, `50+`, and `100+`.
93. Show player snapshot totals with runs, highest score, average, strike rate, milestone counts, wickets, catches, and games.
94. Make player availability game-by-game, not season-wide, and show the scheduled date for each fixture.
95. Let player profile pages show all fixtures, totals, rankings, and involvement across all clubs the player belongs to.
96. Use a more professional typography system with cleaner font sizes and a consistent `Inter` / serif pairing.
97. Make the clubs page and dashboard feel more polished and less oversized.
98. Keep the Admin Center club-specific so selecting another club switches the archive review queue and club data to that club.
99. Show uploaded scorecards clubwise inside the Admin Center, with the archive cards aligned under the Archives area.
100. Let superadmin Amit S review and approve club scorecards before they are added into the club's performance history.
101. Tag uploaded scorecards to the correct club using uploader, captain, player, and match context, and show shared scorecards in both clubs' Admin Center archives when a match belongs to two clubs.
102. Auto-approve scorecards that already have persisted complete JSON, keep only non-JSON or incomplete-extractions in review, and do not treat one-innings uploads as duplicates when the other innings is still missing.
103. Do not leak single-club scorecards into another club's Admin Center archive when the second team is missing.
104. Let a registering player create a new club if it cannot be found, requiring club name, city, and country, and make that user the default club-admin for the new club.
105. Keep the RBAC model centered on `player` by default, `captain`, `club_admin`, and a single `superadmin` identity for Amit S / Amit Sethi only.
106. Keep each club dashboard's player profile list limited to the members actually associated with that club, and seed a newly created club with its creator as the first member.
107. Let captains and club admins manage fixtures, match setup, and player invites for their club, but keep the Admin Center and scorecard review flows superadmin-only.
108. When a captain or club admin invites a player, force that invite into the currently selected club only and do not allow cross-club player creation.
109. Let captains and club admins send WhatsApp fixture and availability reminders to players using their stored mobile numbers so players can update dashboard availability before the game.
110. Let captains and club admins select or deselect the playing XI from the players who have already marked themselves available for the upcoming fixture.
111. Allow a player to hold multiple roles for the same club, and have the auth layer combine those roles for permissions instead of overwriting the previous one.
112. Keep the Admin Center extraction/review JSON on the canonical scorecard template with `meta`, `match`, `innings`, and `validation` so scorecard processing stays consistent.
113. Redesign the sign-in page so the login form stays on the left and the right side shows top batting, bowling, and club leader widgets.
114. Remove the redundant `Upcoming Events` widget from the dashboard and replace that space with a more useful summary panel.
115. Make dashboard season switching load the selected year directly and avoid stale current-year fallbacks.
116. Speed up dashboard rendering by avoiding unnecessary repeated recomputation on every season change.
117. Ensure the Season Setup page shows the club's season list and fixtures for the selected club before CRUD actions.
118. Keep the dashboard registration widget scoped to the signed-in user's club instead of showing every club.
119. Keep registration prompts and club selection consistent with the signed-in club context while preserving the standalone registration page flow.
120. Keep local development as the first validation target and defer Azure deploys until changes are confirmed locally.
121. Treat the backend auth session and `member_id` as the source of truth for the signed-in player; UI aliases and roster order must never choose the player snapshot.
122. Resolve the clubs-page Player Snapshot strictly from the authenticated `member_id`, and prefer no snapshot over the wrong player.
123. Deduplicate club memberships in the profile view so the same club cannot appear multiple times when multiple membership paths overlap.
124. Allow Season Fixtures editing only for future fixtures; past fixtures must be locked in both the UI and API.

## Current behavior summary

- `2026 Summer Season` is the running CricketClubApp season shown in the site header.
- Historical archive scorecards are stored separately from live fixtures.
- Reviewed historical scorecards count as confirmed historical match history in chat/stat answers.
- Chat uses persisted member names, full names, aliases, memberships, fixtures, archives, and rankings as its source of truth.
- The landing page now starts with local registration, primary-club selection, club search, player search, and a followed-player watchlist.
- The selected primary club drives the landing-page focus for upcoming events, upcoming matches, and club stats.
- The app now includes dedicated multi-page flows for `Registration`, `Sign In`, `Club Selection`, `Season Setup`, `Player Availability`, and the club `Dashboard`.
- Club selection shows the selected or primary club first and keeps the rest selectable.
- The club dashboard is now club-focused and removes the in-page club picker so it reflects the selected club only.
- Season setup stores fixtures with their own season year so `2026` and `2027` schedules can coexist.
- Player availability is shown against the selected club's active season fixtures after login.
- The clubs page now shows a player snapshot plus year-wise and club-wise summary tables using cached SQLite stats.
- The clubs page Player Snapshot is resolved from the signed-in player's canonical `member_id`, and it should not fall back to another roster member.
- Player profile club memberships are deduplicated before display so the same club does not appear multiple times.
- Summary milestone counts use `25+`, `50+`, and `100+` bands.
- Player availability is now set per scheduled game, not as one season-wide toggle.
- The player profile is the cross-club career view, while the club dashboard stays club-local.
- TestClub now lives in the normal local runtime on `8090` with a two-innings scorebook fixture and a separate uploaded-image scorecard fixture.
- The sign-in page now uses a split layout with the login form on the left and leader widgets on the right.
- The sign-in page renders batting, bowling, and club leaderboards server-side so it stays visible even before the client script hydrates.
- The dashboard landing page now replaces `Upcoming Events` with a more useful recent-scorecards summary.
- The match center now supports text and voice scoring notes, with browser mic transcription feeding the same saved match commentary stream.
- The live scoring panel now uses a scoreboard-style header with live over chips, batting and bowling tables, and a more professional scoring console layout.
- The scoring console also includes quick delivery shortcuts for common outcomes plus a `Save & next ball` flow for faster manual scoring.
- The dashboard is now an overview hub with widget launcher cards, and each major widget can open as its own page under `/dashboard/widgets/...`.
- The dashboard navigation now follows the mobile app shell: `Home`, `Match`, `Fixtures`, `Squad`, `Assistant`, and `More`.
- The Match area now carries its own local sub-navigation for `Overview`, `Squad`, `Scoring`, `Commentary`, `Stats`, and `Summary`.
- Scorecards, OCR, uploads, settings, admin, and profile live under the secondary `More` menu cards.
- Dashboard season switching now requests the selected year explicitly and is cached to reduce repeated recomputation.
- The Admin Center now renders the selected club first, filters its archive review queue by the active club, and groups uploaded scorecards clubwise for review.
- Season Fixtures now supports editing future fixtures, while past fixtures are locked at both the UI and API layers.
- Historical scorecards stay in the archive-review flow until superadmin approval attaches them back to the correct club or clubs.
- Shared archives can appear in both clubs' Admin Center queues when the scorecard clearly belongs to a two-club match.
- Single-club archives no longer bleed into another club's review queue when the second team is missing.
- Complete JSON imports are auto-approved; partial scorecards and non-JSON uploads remain reviewable until manually confirmed.
- Registration can create a new club when the search does not find a match, and the new club owner becomes that club's default admin.
- Captains and club admins can now notify players through WhatsApp reminders and build a selectable playing XI from the club's available players.
- Players can now carry multiple club roles, and the auth layer unions those roles when calculating permissions.
- The local UI is designed as the web baseline before a later native iPhone app conversion.
- The iOS surface now has a checked-in Xcode project scaffold, and the Android surface has a checked-in Gradle project scaffold, both loading the same live web app for parity.
- The iOS shell can be archived from Xcode and uploaded to TestFlight, but it still needs Apple signing and an app icon asset set before App Store review.
- A starter iOS app icon catalog is checked in under `ios/Assets.xcassets`, ready to be wired in a signing-capable Xcode environment.
- The repo now has an Azure App Service deployment plan checked in under `.azure/plan.md`, App Service infrastructure under `infra/`, and a GitHub Actions workflow under `.github/workflows/deploy.yml`.
- Runtime data such as SQLite, uploads, duplicates, and cache files are treated as server data, while JSON snapshots are kept as the recovery source in Git.
- Dashboard availability now uses the signed-in auth token, and fixture/availability flows are tested against the live selected club rather than the default CricketClubApp.
- The Season Setup page now loads the selected club explicitly and always renders the available season filter list.
- The dashboard registration widget now stays limited to the signed-in club, while the standalone registration page keeps the broader club picker behavior.

## Run locally

```bash
cd /Users/amitsethi/Downloads/HeartlakeCricketApp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app/main.py
```

Open `http://127.0.0.1:8090`

## Project shape

- `app/main.py`: FastAPI routes
- `app/cricket_store.py`: normalization, persistence, dashboard shaping
- `app/cricket_brain.py`: free local question answering
- `app/static/`: local website UI
- `app/static/signin.html`: multi-page sign-in
- `app/static/register.html`: multi-page registration
- `app/static/clubs.html`: primary-club selection
- `app/static/season_setup.html`: club-admin season planning
- `app/static/player_availability.html`: logged-in player availability
- `app/llm_registry.py`: prompt registry loaded from `READMELLM.md`
- `app/llm_service.py`: FastAPI-facing LLM service layer, caching, ranking, and inference
- `ios/`: iOS app surface scaffold, Xcode project, and parity notes
- `android/`: Android app surface scaffold, Gradle project, and parity notes
- `MOBILE_PARITY.md`: shared parity contract for website, iOS, and Android
- `ios/TESTFLIGHT.md`: iOS archive and TestFlight checklist
- `ios/INSTALL_ON_PHONE.md`: TestFlight-only iPhone install path
- `ios/Assets.xcassets/`: starter iOS app icon catalog
- `app/data/seed.json`: CricketClubApp seed data
- `app/data/cricketclubapp.db`: local SQLite database used for persistence at runtime
- `app/uploads/`: accepted scorecard images
- `app/duplicates/`: duplicate-review bundles containing both the original and duplicate file

## Notes

- The site is mobile-friendly and works well as the product baseline for a future iPhone app.
- The web, iOS, and Android surfaces are treated as equal products; any new feature must be reflected in all three unless the README explicitly says otherwise.
- `Imran +2` from the original schedule is stored as an availability note saying he is bringing two guests.
- The Assistant header shows a compact status chip beside the Assistant title with a colored dot and text: solid green `Online`, blinking green `Thinking`, blinking red `Connecting`, and solid red `Offline`.
- The status chip sits beside the Assistant title, and the `Clear chat` button resets the browser conversation state plus cached LLM answers.
- If Ollama is running locally, the Assistant uses it; when the forecast reply is too vague or hallucinates unsupported details, the app falls back to a grounded year-by-year trend summary instead of a made-up projection.
- The prompt library in `READMELLM.md` is loaded into the runtime registry and indexed into the LLM document corpus for inference.
- The LLM service layer exposes `/api/llm/status`, `/api/llm/prompts`, `/api/llm/documents`, `/api/llm/reindex`, and `/api/llm/infer` for prompt inspection, corpus refresh, and direct inference.
- `/api/llm/cache/clear` resets the shared LLM query cache so the next chat starts fresh.
- The chat pipeline now uses chunked context selection, optional Ollama embeddings for retrieval ranking, configurable sampling for forecast answers, and safety checks that avoid inventing unsupported numbers.
- The chat pipeline also applies a small profanity/content filter so responses stay cricket-focused and respectful.
- Saving the store refreshes the indexed LLM corpus, including prompt docs, club summaries, member summaries, fixtures, and archive scorecards.
- Existing images dropped into `app/uploads/` are auto-imported into the archive list.
- Duplicate files are moved into `app/duplicates/` for manual review, with a copy of the matched original staged beside them.
- The local LLM also powers grounded predictive analysis for club and player outlooks across current and future seasons, with year-trend fallbacks when the model gets too vague.

## Azure LLM

For Azure, the web app stays on App Service and Ollama runs separately in Azure Container Instances.

- Deploy Ollama with [`scripts/deploy_ollama_aci.sh`](scripts/deploy_ollama_aci.sh)
- ACI template: [`infra/ollama-aci.yaml`](infra/ollama-aci.yaml)
- Operator notes: [`.azure/ollama-aci.md`](.azure/ollama-aci.md)
- The ACI flow pulls both the chat model and an embedding model (`nomic-embed-text` by default) so the web app can do grounded retrieval ranking when embeddings are available.
- Current live Ollama endpoint: `http://cricketcanclubs-ollama-cc260508.canadacentral.azurecontainer.io:11434`
- The Azure Files share behind Ollama is intentionally capped at `10 GiB` so model storage stays small and predictable.
- For a fresh redeploy, set `OLLAMA_BASE_URL` to the ACI endpoint returned by the deploy script. The App Service in Azure already points at the current live endpoint above.
- The Assistant status chip reads `/api/health` and flips between the four live states depending on Ollama availability and chat request phase.

This keeps the web app lightweight while giving the chat and archive review flows a real model backend.

The same registry and corpus indexing flow is used for scorecard ingestion:

- uploaded archives and review payloads are re-indexed into the LLM document corpus on save
- prompt registry entries from `READMELLM.md` are kept as first-class inference docs
- query cache entries are stored in SQLite so repeat questions can reuse earlier responses safely
- optional embeddings rank the most relevant club, player, fixture, and archive documents before inference

## Azure Login

If you need to deploy with the direct App Service zip path, the CricketClubApp Azure tenant is:

- Tenant ID: `44402a74-5c2e-4982-a6fb-e70bb39c7d8a`

Use it with:

```bash
az logout
az cloud set --name AzureCloud
az login --use-device-code --tenant 44402a74-5c2e-4982-a6fb-e70bb39c7d8a
az account set --subscription 9fdb812c-a846-4890-a27d-b99edc274a5e
```

Then use [`scripts/deploy_azure.sh`](scripts/deploy_azure.sh) for the zip deploy.

## Chat Prompt Examples

Use the website AI box with natural-language questions like these. They should work for any stored player name, full name, or alias:

- `What is <player name> full name?`
- `How old is <player name>?`
- `What is <player name> phone number?`
- `How many matches <player name> has played so far?`
- `How many matches <player name> has played in 2025 and in which months?`
- `How many matches <player name> played in Sep?`
- `How many matches both <player one> and <player two> played?`
- `What batting order <player one> and <player two> bats in the team?`
- `What is the best batting order for <player name>?`
- `Search <player name> and show their stats`
- `Show all stats for <player name>`
- `Which scorecards mention <player name>?`
- `Which scorecards mention <player name> in 2025?`
- `Who is the top ranked player with runs?`
- `Who has got most wicket?`
- `Who has taken most number of catches?`
- `Who are the top 5 batters with runs?`
- `Which players are rarely available?`
- `Which players are most consistent with last year availability by playing most games?`
- `Predict TestClub batting, bowling, and fielding outlook for 2026 and 2027`
- `Forecast Amit S's runs and batting average for the next season`
- `What is the projected top batter for TestClub next year?`
- `How is Amit Sethi's performance going to be in 2026 season?`
- `Who should be the captain of Coca Cola team in 2026?`
- `What is the next match?`
- `Show old scorecards from 2025`
- `Follow <player name>`
- `Set CricketClubApp as my primary club`

## Archive Review Prompt Examples

When reviewing imported historical scorecards, use prompts or pasted review notes in this style:

- `CricketClubApp 182/8 vs Coca Cola, extras 36`
- `Amit S 68, John 24, Checkley 4, Navesh 8, Steve 10`
- `Map Amit to Amit G only when the scorecard clearly refers to Amit Gaba`
- `Treat Amit S and Amit Sethi as the same saved player only when that alias exists in the database`
- `Use the scorecard date if visible; otherwise fall back to image metadata`

## Admin Center Controls

- Superadmin-only Admin Center actions include club cleanup and player cleanup.
- Delete a player from the selected club only after confirming they should be removed from that club roster.
- Delete a club only from the superadmin Admin Center, and keep shared archives visible for any remaining clubs they belong to.
- Keep club/player delete operations club-scoped and make sure auth references are cleared before the store is re-saved.

## Access Control Sanity

- Dashboard, Clubs, Season Setup, Player Availability, Player Profile, and Admin Center must redirect to `/signin` when there is no valid session.
- Admin Center must stay superadmin-only.
- In Admin Center, club and player delete controls should appear before the fixture editor for discoverability.
- Browser cache-busting must be updated whenever a page bundle changes so stale JS does not hide admin controls.

## Deployment Workflow

- Test locally first before any Azure deploy.
- Azure deploys are manual and require explicit approval by setting `DEPLOY_APPROVED=yes`.
- The deploy script packages the current working tree directly to Azure App Service, so GitHub commits are not required for deployment.

## Name Resolution

- Player identity comes from persisted data in SQLite and cache, not hard-coded name maps.
- Matching uses the saved `name`, `full_name`, and `aliases` fields on each member record.
- If you want a new alias to be recognized by chat, archive review, and score extraction, add it to the player profile in the website so it is persisted.
