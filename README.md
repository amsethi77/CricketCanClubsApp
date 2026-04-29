# CricketClubApp

Local-first website for CricketClubApp. This is the web version we can test quickly before turning the same product into a native app.

## What it includes

- Team member profiles with age, role, picture URL, phone, email, and notes
- Season schedule with visiting teams
- Match setup with captain, venue, toss, scorer, and status
- Player availability tracking by match
- Live scoring and scorecard updates
- Player performance tracking for runs, wickets, catches, fours, and sixes
- Text commentary and voice transcript capture per match
- WhatsApp launch link for match coordination
- Free AI-style Q&A over the stored club data
- Scorecard image upload plus archive-review flow for offline score recovery
- Ball-by-ball innings scorebooks with 11 batters and 11 bowlers per innings
- Local viewer registration with mobile or email
- Primary-club selection and club-first landing experience
- Club search, player search, quick stats, and followed-player watchlist
- Landing-page highlights for upcoming events, matches, and club stats

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
11. Add live voice commentary, text commentary, speech-to-text, and persistence per match.
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
- Summary milestone counts use `25+`, `50+`, and `100+` bands.
- Player availability is now set per scheduled game, not as one season-wide toggle.
- The player profile is the cross-club career view, while the club dashboard stays club-local.
- The Admin Center now renders the selected club first, filters its archive review queue by the active club, and groups uploaded scorecards clubwise for review.
- Historical scorecards stay in the archive-review flow until superadmin approval attaches them back to the correct club or clubs.
- Shared archives can appear in both clubs' Admin Center queues when the scorecard clearly belongs to a two-club match.
- Single-club archives no longer bleed into another club's review queue when the second team is missing.
- Complete JSON imports are auto-approved; partial scorecards and non-JSON uploads remain reviewable until manually confirmed.
- Registration can create a new club when the search does not find a match, and the new club owner becomes that club's default admin.
- Captains and club admins can now notify players through WhatsApp reminders and build a selectable playing XI from the club's available players.
- Players can now carry multiple club roles, and the auth layer unions those roles when calculating permissions.
- The local UI is designed as the web baseline before a later native iPhone app conversion.
- The repo now has an Azure App Service deployment plan checked in under `.azure/plan.md`, App Service infrastructure under `infra/`, and a GitHub Actions workflow under `.github/workflows/deploy.yml`.
- Runtime data such as SQLite, uploads, duplicates, and cache files are treated as server data, while JSON snapshots are kept as the recovery source in Git.
- Dashboard availability now uses the signed-in auth token, and fixture/availability flows are tested against the live selected club rather than the default CricketClubApp.

## Run locally

```bash
cd /Users/amitsethi/Downloads/HeartlakeCricketApp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app/main.py
```

Open `http://127.0.0.1:8091`

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
- `app/data/seed.json`: CricketClubApp seed data
- `app/data/cricketclubapp.db`: local SQLite database used for persistence at runtime
- `app/uploads/`: accepted scorecard images
- `app/duplicates/`: duplicate-review bundles containing both the original and duplicate file

## Notes

- The site is mobile-friendly and works well as the product baseline for a future iPhone app.
- `Imran +2` from the original schedule is stored as an availability note saying he is bringing two guests.
- If Ollama is running locally, the AI badge shows the local model; otherwise the heuristic assistant still works.
- Existing images dropped into `app/uploads/` are auto-imported into the archive list.
- Duplicate files are moved into `app/duplicates/` for manual review, with a copy of the matched original staged beside them.

## Chat Prompt Examples

Use the website AI box with natural-language questions like these:

- `What is Amit S full name?`
- `How old is Amit G?`
- `What is Amit S phone number?`
- `How many matches Amit S has played so far?`
- `How many matches Amit S has played in 2025 and in which months?`
- `How many matches Amit S played in Sep?`
- `How many matches both Amit S and Amit G played?`
- `What batting order Amit S and Amit G bats in the team?`
- `What is the best batting order for Amit S?`
- `Who is the top ranked player with runs?`
- `Who has got most wicket?`
- `Who has taken most number of catches?`
- `Who are the top 5 batters with runs?`
- `Which players are rarely available?`
- `Which players are most consistent with last year availability by playing most games?`
- `What is the next match?`
- `Which scorecards mention Amit S?`
- `Show old scorecards from 2025`
- `Search Amit Gaba and show his stats`
- `Follow Amit Sethi`
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
