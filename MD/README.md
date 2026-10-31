# CricketClubApp

Local-first CricketClubApp product with a web app plus matching iOS and Android app surfaces. The three surfaces are kept in lockstep so the same cricket workflows are available everywhere.

## Instructions for AI tools (read first)

Any AI assistant or coding tool working on this repository (Claude, ChatGPT, Copilot, Cursor, Gemini, etc.) must follow these rules:

1. **Document every change in this README.md.** When you add or change a feature, page, API, data rule or workflow, add or update the matching section below (and add a dated line to "Change log") in the same change. Future developers and AI tools rely on this file as the single source of truth.
2. **Record the user's request.** Add the requirement, in plain words, to "Prompt And Requirement Log" so the reason behind the behaviour is kept.
3. **Keep the three surfaces in lockstep.** The iOS and Android apps load these web pages, so web changes must work at phone width (390px) as well as laptop width.
4. **Never commit local data or secrets.** Files in `app/data/` (`*.db`, `*.db-shm`, `*.db-wal`, `*_cache.json`, `.stats_version`), `app/uploads/` and the `.env` file (Stripe keys) stay out of git.
5. **Test before you hand over:** restart with `python app\main.py`, check the pages you touched on laptop and phone widths, and note how to test in the README section you updated.

The same rules are in `AGENTS.md` and `CLAUDE.md` so every tool picks them up. If you use GitHub Copilot, copy `AGENTS.md` to `.github/copilot-instructions.md`.

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
- Cricinfo-style digital scorecards browsable by game date (`/scorecards`)
- Redesigned public home (`/live`) and signed-in Home (`/dashboard`)
- Quick Score (`/score`): phone-first ball-by-ball scoring with big buttons, voice and shorthand
- AI Assistant: chat agent that answers questions, saves scores typed or spoken, uploads scorecard photos and sends availability requests
- In-app notifications (bell icon): availability requests, live score alerts and results
- Player/club insights: form, predictions, improvement tips, suggested playing XI and season outlook
- Plans (`/pricing`): Free (default) and Pro ($9/month or $90/year) with feature limits, monthly upload quotas, one free AI match on Free, a 60-day trial for existing members, Stripe Checkout (off until keys are added) and admin plan management
- AI Live Scorer (Pro, or the free AI match): say or type "wide, then two runs" in Quick Score and the balls are added for you

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

### September 2026 requests
- Navbar: no More on laptop unless links don't fit; on phone More sits at the edge. Profile and Admin live inside the account (initials) button; Assistant sits at the bottom right.
- Signed-out visitors can open a public Clubs page, search the site and switch dark/light mode.
- Digital scorecard like Cricinfo, available from archives by game date; approved archives only; public; original photo as a tab.
- Home page redesign for both public and signed-in users (live and recent matches, latest scorecards, join/sign-in banner); white/off-white banners.
- AI for chatting about clubs and players, with predictive analysis and recommendations for players and clubs to improve rankings and performance.
- Matchday tile must not show a past date: if there is no new fixture, show the last score.
- Live scoring must be very easy.
- AI Muse agent: chat with players/admins, add/upload scorecards, accept scores by text or voice, send availability requests and live score alerts (in-app notifications).
- Any instructions given to an AI tool must ask it to record the change in README.md for future reference.
- AI Muse should also be available before login, as a safe read-only version (public scores, results, scorecards, stats) that asks visitors to sign in for actions.
- (Oct 2026) Scores and availability of past-dated matches must not be editable.
- (Oct 2026) Past games must not be shown as upcoming.
- (Oct 2026) The AI assistant must be back and answer through the LLM model the app already had (it had been renamed to AI Muse).
- (Oct 2026) AI Muse should act like an assistant that carries out tasks on command (score updates, availability, etc.), like Meta's Muse.
- (Oct 2026) The AI assistant should also be available before sign-in.
- (Oct 2026, feedback) Show the full menu only to signed-in members on a paid plan (Super or Premium); Free members can score new matches and view, and see the other features by choosing a plan.
- (Oct 2026, feedback) Clean up the UI so it is easy to navigate and understand.
- (Oct 2026, feedback) Allow new matches without sign-in or a team schedule, but both teams' line-ups must be done before scoring starts.
- (Oct 2026, feedback) The Home page should show live and past matches, not just matches and latest scorecards.
- (Oct 2026, call with Amit Sethi, soft launch for Diwali) Registered users use scoring and AI according to their plan. Very easy navigation; remove features people don't need. Scorecard upload by the captain or club admin. "Upcoming matches" shows everything upcoming plus player availability. Free is the default plan. Monthly $9; yearly cheaper ($90, 2 months free); monthly is pre-selected. Not registered: no sign-in, manual scoring still allowed. Insert clean data for the soft launch. Fix duplicate scorecards with smart detection (AI/Ollama). After a scorecard upload: if it isn't proper, send it to the site admin; if it has errors, alert the players; show the complete digital scorecard after upload. App tour.
- (Oct 2026, decisions) One paid plan **Pro: $9/month or $90/year** replaces Super and Premium. Free users get **one free AI match**. Menu: merge Fixtures + Availability into **Matches**, hide Performances, move Clubs + Profile into the account menu, merge Archives into **Scorecards**.
- Subscription model (#7, from "Cricket App Subscription & Feature Model"): keep live scoring, player/club stats and scorecard viewing free; Free 2 scorecard image uploads a month; Super $4.99/month (5 uploads, multi-club, rosters, availability, Playing XI, alerts, live score updates, AI assistant, analysis); Premium $100/year (unlimited uploads, advanced AI, AI Live Scorer that turns spoken ball-by-ball events into structured events for the scoring engine, match intelligence, cross-club stats, advanced analysis, retro-score help, priority support). Decisions: pay with Stripe (switched off until keys are added; site admins set plans by hand until then); existing users get 60 days of Premium free, new users start on Free.
- (Oct 2026) Default all users to Premium for now, make the default configurable, and switch it to Free at launch.
- (Oct 2026) In Admin Center scorecard review, show the same digital scorecard snapshot as the Scorecards section, retain the editable JSON, and display the original uploaded image at the same time.
- (Oct 2026) Rename AI Muse to AI Assistant throughout the app.
- (Oct 2026) Improve Admin Center scorecard extraction with computer vision/Ollama and populate the full review JSON from scorecard images.
- (Oct 2026) Run Ollama locally for AI Assistant replies and scorecard image extraction; keep the app on the local Ollama endpoint and use local chat and vision models.
- (Oct 2026) Show the uploaded scorecard image itself in Admin Center review instead of exposing its URL.
- (Oct 2026) Reset scorecard and player-performance data across all years, including live fixtures, then restart image-based scorecard processing with 2024 only.
- (Oct 2026) Reset all score data again across every year.

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
125. Keep every page fixed to the screen width: no pinch/double-tap zoom on phones and no sideways scrolling; also block laptop zoom (Ctrl +/−, Ctrl + wheel), keeping Ctrl + 0 to reset.
126. On our paper scorecards "RO" means Retired Out, not Run out; read and show it that way (with a setting in case a club uses RO for run out).
127. Keep the sign-in page simple (just the sign-in form). Show the app tour only after the first sign-in of each account, as a list of the things to do first.
128. New users: show Live scores before sign-in, then Home right after sign-in (Clubs only if they still need to pick a club), followed by the first-time tour.
129. Before sign-in show a short menu (Live, Fixtures, Scorecards, Rankings, Sign In); keep Score, Clubs, Plans and Register available under More.
130. Keep More at the right without Dark mode, put Sign out on its own, explain the CC logo with the app name, and keep the Live page to the essentials (welcome, featured match, results, coming up).
131. Restrict features before sign-in (view and manual scoring only, no AI) and for Free users (one free AI try covering AI Assistant, AI Scorer or one AI-read scorecard photo; everything else AI is Pro).
132. The AI Assistant must answer basic questions (greetings, cricket rules, how to use the app) as well as club questions, never ask a signed-in person to sign in, and open as a full-height panel on the right.
133. The assistant should look like it is thinking ("…" for a few seconds) and then type its answer; the app tour is only for first-time sign-ins, not an account-menu item.
134. Re-processing scorecard images in the Admin Center must extract the handwritten scorecard (AI reader), as scorecard extraction is the main feature.
135. Train the AI to read scorecards properly: learn names people correct (e.g. Meshad → Heshad), read RUNS(BALLS) like 4(17) as 4 runs off 17 balls, and never misread the year (2026 read as 2020).
136. (Amit, Oct 19) Sign-in must show the player name field, sign-in must go to club selection, and club data must be easy to find: put back the name field, send people to /clubs after sign-in, and add Clubs and Stats to the top menu. Don't revert the other work.
137. Stats is seen by every signed-in player (basic numbers); Pro unlocks more detail (season-by-season trends). Train the AI Assistant to do better.
138. Delete a scorecard and upload it again (the duplicate check blocked re-uploading the same photo).
139. Reading a scorecard photo takes too long - make it faster.
140. (Amit + Dhruvika, Oct 20) Use all previous images to train the reader, clean up the data and re-extract all previous scorecards to check it works; the training must be committed to git so local and Azure copies use it; it must show in the Admin Center.
141. (Dhruvika, Oct 26) "Train it to do better than this, train it properly this time": the AI reader must learn from checked cards, not only from rules.
142. (Amit + Dhruvika, Oct 26) Launch the website, the iPhone app and the Android app together on Diwali (Nov 8); fully native screens after launch.
143. (Amit, Oct 26, after the first Azure deploy) A club's Home must show only its own scorecards; menus must be the same everywhere; "Next match" must not show past games; Plans not showing (launch mode, see "Launch: everyone on Pro").
144. (Dhruvika, Oct 27) App tour that works inside the phone apps, a welcome tour for first-time visitors, a privacy policy page and "Delete my account" (both needed for the app stores).
145. (Dhruvika, Oct 28) "Go with React Expo": one Expo / React Native app for iPhone and Android instead of separate Swift and Kotlin apps (iPhone builds in the cloud, no Mac needed).
146. (Amit + Dhruvika, Oct 28) Before moving to a cloud database, saving must write only what changed, not rewrite every table on every save.
147. (Amit, Oct 29) "Manual scoring is somewhat tedious. Fix the live scoring and make it really easy and interesting": tap names instead of typing, fewer pop-ups, quicker line-ups, fix any ball, celebrations for fours, sixes, wickets, fifties and hundreds. Also (Amit): stay on SQLite for now; later a daily copy of production data to Azure SQL so it can't be lost.
148. (Amit, Oct 29, on Azure) "Not allowing to start the match": saving 11 + 11 line-ups said "Match not found."; each team must have at most 11 players; the line-up players must be offered as a list to pick batters and bowlers, not a text box.
149. (Amit, Oct 29) The public scoreboard doesn't show the score completely; batting and bowling stats should be one row per player, not one box per number.
150. (Dhruvika, Oct 29) The time is GMT; correct it (a match started at 12:08 AM showed 4:08 AM).
151. (Dhruvika, Oct 29) "Check every single detail, test it fully" (before Amit deploys the scoring changes to Azure).
152. (Amit, Oct 29) Show only the last 10-12 balls in one single row; hide the rest or move them to "More".
153. (Dhruvika, Oct 29) "On winning do hurray!!" - a big celebration when a match is won. Also seen in her test: RCB 28/11 (an 11th wicket was saved after the innings was over).
154. (Dhruvika, Oct 29) "Something went wrong here, check" (Heartlake vs GT test match).
155. (Dhruvika, Oct 29) "The match was over but it still showed that GT need 29 from 15 balls".
156. (Dhruvika, Oct 29) Give the option of selecting the captain, wicket keeper and vice-captain when choosing the players for a match.
157. (Dhruvika, Oct 29) "Not like this, don't make it more complicated": choose captain, VC and WK right where the players are picked, not in separate menus.
158. (Dhruvika, Oct 29) "Any other simpler and easier option? This looks so cluttered" (the C / VC / WK buttons on every player).
159. (Dhruvika, Oct 29) "When I start a match with GT or RCB again it takes me to the previous scorecard"; "on the navbar Plans takes me to Home - I want you to show Plans there".
160. (Dhruvika, Oct 29) Ask the players about their availability when a match is fixed, notify them about it, and notify them about their upcoming match.
161. (Amit, Oct 30) The live scorecard font size and layout should look like the big cricket score apps (Cricbuzz screenshot), and live scoring should be quick for the Saturday game.
162. (Dhruvika, Oct 30) Use the same font as Cricbuzz (Roboto) in the whole app.
163. (Dhruvika, Oct 30) A 1-over match let the other team bat 2 overs. Both teams must get the same overs.
164. (Dhruvika, Oct 30) The Live tab should look exactly like Cricbuzz: team rows, "need X runs in Y balls", CRR / RRR / last 5 overs, the balls by over with "15th · 3 RUNS", win probability, and BATTING / BOWLING tables with R B 4s 6s SR and O M R W ECON.
165. (Dhruvika, Oct 30) An uploaded scorecard showed "c Singh b Singh" for "c & b Singh".
166. (Dhruvika, Oct 30) Train the AI scorecard reader well so mistakes like "c Singh b Singh" don't happen.
167. (Dhruvika, Oct 30) The uploaded scorecard page should use the same font, font size and layout as the live page (Cricbuzz).
168. (Dhruvika, Oct 30) An uploaded scorecard must look exactly like a manually scored match's scorecard - no difference.
131. Find duplicate scorecards smartly with AI (Gemini, or Ollama offline), not only exact matches.

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
- The Admin Center now renders the selected club first, filters its archive review queue by the active club, and groups uploaded scorecards clubwise for review. Each archive review shows the same Scorecards-page snapshot beside the editable JSON, with the uploaded original image also visible at the same time.
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

Use the repository startup script from the project root:

```bash
./startup.sh
```

The script creates `.venv` if needed, installs `requirements.txt`, and starts the FastAPI server on port `8091` by default. You can override the port when needed:

```bash
PORT=8092 ./startup.sh
```

Open `http://127.0.0.1:8091`.

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

## September 2026 update: UI redesign, scorecards and AI features

This section documents the work done in September 2026. See "Change log" at the end for dates.

### Navigation and look and feel
- **Public header** (`static/public_header.html/js`): LIVE, Fixtures, Rankings, Scorecards, Clubs, Sign In, Register. On phones it becomes a Cricinfo-style layout: ☰ menu drawer with search, ⚙️ settings sheet (Change Mode, Sign In/Register) and a bottom tab bar. Logic lives in `static/site_tools.js`.
- **Search and dark/light mode** on every page (`site_tools.js`, `GET /api/public/search`). Search never returns phone numbers, emails or ages. Dark mode inverts the page with a CSS filter; photos and the dark banners are flipped back.
- **Signed-in navbar** (`static/shared_header.html`, `multipage.js`): shows as many links as fit and puts the rest under More. Profile, Admin center, club switch and Sign out are inside the account (initials) button. Scoring opens Quick Score.
- **Shared look** for all signed-in pages: `static/app_polish.css` (white cards, one heading font, consistent inputs/buttons, status messages as a small toast). It is linked statically in each page's `<head>` to avoid a flash of old styles.
- **Sign In / Register** pages: `static/signin.css`, `static/register.css` (Register is a 3-step card).
- **Public Clubs page** for signed-out visitors: `GET /clubs` serves `public_clubs.html` (`GET /api/public/clubs`).

### Digital scorecards (`/scorecards`)
- `GET /api/public/scorecards?date=&club_id=&year=` lists **approved** archive scorecards, newest first; `GET /api/public/scorecards/{id}` returns one Cricinfo-style card (batting, bowling, extras, did-not-bat, match details, original photo URL).
- Pages: `static/scorecards.html/js` (list grouped by month, date picker with "closest dates", club and season filters) and `static/scorecard.html/js` (innings tables + "Original scorecard" photo tab). Styles: `static/scorecards.css`.
- Archive review uses the same shared `scorecard.js` renderer and `scorecards.css` for a digital snapshot beside the editable extraction JSON; the uploaded original image is rendered directly in the review panel, without displaying its URL. HEIC/HEIF originals are converted to browser-compatible JPEG previews while preserving the original upload; an original-photo tab remains included in the snapshot. The three panels sit side by side on wide screens and stack on phones. Pending previews are returned only from the superadmin-protected Admin Center queue.
- Scorecard image extraction uses local Ollama vision when a supported model is installed. It submits the full page plus enhanced header, batting-table, and bowling-table crops and writes the model's innings, batting, bowling, dismissal, extras, and match fields into the review JSON. Vision models are auto-detected (including tagged Ollama names); `ARCHIVE_VISION_MODEL` can select one explicitly. On Windows, install Ollama, pull `qwen3-vl:8b`, verify it appears in `http://127.0.0.1:11434/api/tags`, then use **Re-extract** on a pending archive. Re-extraction clears stale extraction JSON before regenerating it. If no local vision model or OCR tool can read the image, the review summary says so and keeps the item pending; all AI-generated figures still require admin verification.
- Data comes from the best available copy of each archive's extraction (reviewed JSON, template, imported performances, draft scorecard). Missing figures show as "–".

### Home pages
- **Public home** `/live` (`static/home.js`, `static/home.css`): match strip (Live / Results / Upcoming), off-white banner with featured match, latest scorecards, recent results, coming up, join banner.
- **Signed-in Home** `/dashboard` (`static/dashboard_home.js/css`, only on the overview): welcome card with quick actions, match strip, latest scorecards, and an **AI Assistant** card at the bottom. Panels that duplicated the navbar (scoring keypad, main menu, registration form) are hidden on Home.
- **Matchday tile**: if there is no upcoming fixture it shows the **last match that has a score** (both totals + result) instead of an old date (`renderLastMatchHero` in `app.js`).

### Quick Score (`/score`)
- Files: `static/quick_score.html/js/css`. APIs: `GET /api/quick-score/fixtures`, `GET /api/quick-score/{match_id}`, `POST /api/quick-score/start` (creates today's fixture), plus the existing `POST /api/matches/{id}/scorebook/setup`, `POST .../scorebook/ball` and `DELETE .../scorebook/ball` (undo).
- Flow: pick today's match (or "Start a match now") → choose batting side, openers and bowler → score with big buttons `0 1 2 3 4 6 / Wd Nb Bye LB / W / Undo`.
- Strike rotates automatically on odd runs and at the end of each over; after 6 legal balls it asks for the next bowler; W opens a pop-up for how out, fielder and the new batter; 2nd innings shows the target and required rate.
- **Voice scoring** (Chrome/Edge): "dot", "single", "two", "four", "six", "wide", "no ball", "bye", "leg bye", "bowled", "caught", "LBW", "run out", "undo". **Shorthand**: type `1 4 0 wd 6 w`.
- Taps are queued and saved in order ("Saving 2 balls…"), so fast scoring never loses a ball. Scoring is open only on the match day (rule in `_scorebook_is_open`); past games go through AI Assistant or Archives.
- Performance: `canonical_archive_uploads` now returns a marked list that isn't re-processed, which cut each save from ~8–19 s to ~2 s.

### Insights and predictions (`app/cricket_insights.py`)
- Player form (In form / Steady / Out of form from the last 5 innings vs the player's normal level), trend, next-innings projection with range and % chance of 25+/50+, and improvement tips with the reason from the stats.
- Club record, rank, batting depth, wicket takers, next-match win chance, and tips to climb the rankings.
- **Suggested playing XI** from available players (keeper, up to 5 bowling options, best batters, batting order) and **season outlook** (win chance per remaining fixture, projected wins/rank, projected top scorers).
- APIs: `GET /api/insights/me`, `GET /api/insights/player/{key}`, `GET /api/insights/club/{key}` (signed-in only). Shown on the Assistant page (`static/insights.js/css`) and used by the chat.
- Nothing is "trained": numbers are recomputed from stored matches and approved scorecards, so they improve automatically as more data is added.
- Strike rate only counts runs from innings where balls faced were recorded (`sr_runs` in `cricket_store.py`); saved stats are rebuilt once on first start after this change (`app/data/.stats_version`).

### AI Assistant and notifications
- **AI Assistant** (`app/muse.py`, `static/muse.js/css`, loaded on every signed-in page by `multipage.js`): floating "✨ AI Assistant" button (bottom right) that opens a chat panel with Chat and Alerts tabs, 🎙️ voice input and 📎 photo upload. The old Assistant button is replaced by it; the Home page also has an AI Assistant card.
- `POST /api/muse` handles actions before falling back to the normal assistant (`answer_question`):
  - **Score entry by text/voice**, e.g. `Heartlake 145/6 in 20 overs, Imran XI 120/9. Heartlake won by 25 runs. Amit S 45 off 30, Nick 3 wickets, John 2 catches` → shows a draft; **Confirm** calls `POST /api/muse/confirm-score` (needs `manage_scorecards`), which saves the scorecard + performances and sends a result alert.
  - **Availability request**: "Ask everyone for availability for the next match" (needs `manage_fixtures` or `manage_players`) → notification to every club member with a link to `/player-availability?fixture_id=…`.
  - **Availability summary**: "Who is available for the next match?"
  - **Photo upload**: 📎 posts the image to `POST /api/scorecards/upload` (goes to Archives for review).
  - Help replies for live scoring and alerts.
- **Notifications** are stored in SQLite tables `app_notifications` and `app_notification_reads` (created automatically). APIs: `GET /api/notifications`, `POST /api/notifications/read` (`{ids:[…]}` or `{all:true}`). The 🔔 bell (laptop header) and the Alerts tab poll every 30 s; "Turn on browser alerts" enables pop-up notifications while a tab is open.
- **Live score alerts** are created automatically after each ball (`muse.live_score_events`): match started, second innings started, wicket, 50/100 for a batter, innings over. Results saved through AI Assistant also send an alert.
- **Public AI Assistant (signed-out visitors, read-only)**: `static/muse_public.js` is loaded by `public_header.js` on public pages (Live, Fixtures, Rankings, Scorecards, Clubs, match pages; not Sign In/Register). It calls `POST /api/public/muse` (no login), which answers only from public data: live scores, latest results, scorecards by date ("Scorecard for 19 Oct 2024"), club list, how to register, player stats/form/predictions, club rankings and match-up win chances. Anything that needs an account (saving scores, photo upload, availability requests or replies, alerts, team selection) replies "You need to sign in…" with Sign in / Register buttons. It never returns contact details, availability or pending-review information.
- Email / WhatsApp / SMS are not connected yet (in-app only, by choice). A provider such as SendGrid or Twilio can be added later in `_notify()` in `main.py`.

### AI Assistant as an agent (Oct 2026)
- The floating button and chat panel are labelled **✨ AI Assistant**. Questions go to the same LLM assistant as the Assistant page (`cricket_brain.answer_question`: Ollama when it is running, otherwise the built-in data assistant). The panel header shows the model ("Powered by llama3…" or "AI model offline · answering from club data"), from `GET /api/llm/status`.
- **Local Ollama setup (Windows):** install Ollama (for example, `winget install --id Ollama.Ollama --exact`), start the Ollama service, then pull `llama3.2:latest` for chat and `qwen3-vl:8b` for scorecard vision. Ollama listens at `http://127.0.0.1:11434` by default; the app reads `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `ARCHIVE_VISION_MODEL` if overrides are needed. Check `http://127.0.0.1:11434/api/tags`, then `/api/health` or `/api/llm/status` and confirm the provider is `ollama`. Without a responding local service and model, the app falls back to its built-in data assistant and image extraction cannot use vision.
- AI Assistant **carries out tasks** you ask for (`app/muse_agent.py`):

| Say | Task (tool) | Who can |
|---|---|---|
| "Mark me available for Saturday", "I can't play on Sunday", "count me in" | `mark_availability` (you) | any linked player |
| "Rahul and Nick are out for the next match", "mark Amit S as maybe" | `mark_availability` (others) | captain / club admin |
| "Ask everyone for availability" | `request_availability` (bell notification) | captain / club admin |
| "Remind the players who haven't replied" | `remind_pending` | captain / club admin |
| "Who is available for Sunday?" | `availability_summary` (answers straight away) | anyone |
| "Pick the best XI for the next match" | `pick_xi` (saves players who said Available/Maybe) | captain / club admin |
| "Add a match vs Imran XI on Oct 12 at 10am, 20 overs" | `create_fixture` (today or later only) | captain / club admin |
| "We are 85/3 after 12 overs", "They are 40/2 after 6 overs" | `live_update` (today's match + live alert) | scorer / admin |
| "Heartlake 145/6, Imran XI 120/9, Heartlake won by 25 runs" | `record_result` (today's match only) | scorer / admin |

- **Plan → Confirm → Done.** `POST /api/muse` returns the plan with an `action` (`{tool, args, confirm_label}`); the chat shows **Confirm** and **Cancel**. Nothing changes until Confirm calls `POST /api/muse/execute`, which checks the person's role, their plan and the past-match lock again before doing anything, and writes an audit row (`muse.execute`).
- Commands are recognised by rules first (`muse_agent.parse_command`, dates like "Saturday", "next Sunday", "Oct 12", times like "10am"). If the rules don't recognise something that looks like a command ("please…", "can you…", "set…") and Ollama is running, the LLM is asked to pick the tool (`muse_agent.llm_plan`, JSON output). Anything else is answered by the LLM assistant.
- Running tasks through AI Muse is part of **Pro** (`ai_assistant`; Free users get one free AI match); "who is available?" and questions work on every plan.
- **Prompt file fix:** `READMELLM.md` (the LLM prompts) moved to `MD/READMELLM.md`; `app/llm_registry.py` now looks in `MD/` first and then the repo root, and no longer crashes if the file is missing. Before this fix, adding a fixture or asking the assistant could fail with "No such file … READMELLM.md".

### AI Assistant before sign-in (Oct 2026)
- The public assistant (`static/muse_public.js`, loaded by `public_header.js`) now shows a **✨ AI Assistant** button on every public page, including **Sign In** and **Register** (on phones it sits above the bottom tab bar).
- `POST /api/public/muse` still answers live scores, results, scorecards by date, clubs, rankings, player stats and how to join from its own rules. Anything else now goes to the **LLM assistant** (`answer_question`) on a public-only copy of the data (`_public_chat_store`: no phone, email, age, notes, availability, playing XI or scorecards waiting for review), scoped to the club named in the question, and the reply is scrubbed for anything that looks like an email or phone number (`_public_scrub`).
- Tasks ("mark me available", "update the score", "add a match"…) reply with Sign in / Register buttons.
- The assistant's "next match" answers now only use today's or future fixtures (`_next_upcoming_fixture` in `cricket_brain.py`), so a past game is never called the next match.

### Plan-based menu (Oct 2026)
- Since the soft-launch clean-up everyone sees the same five items (see "Simple menu and app tour"); the plan decides what **Matches** opens and whether the Assistant is shown. The account menu shows "Free plan · Upgrade" or "My plan · Pro".
- **Pro** members and site admins get everything: availability, the fixture manager, the Assistant page and (site admins) Admin. Free members see the Assistant while their one free AI match is still open (`ai_trial_open` in the user payload).
- Players of a club whose captain or club admin is on a paid plan also see **Availability** (`club_paid` in the user payload).
- `multipage.js` (`PAID_NAV`, `navAllowed`, `syncPlanNav`) hides the links in the top menu, the More menu and the phone tab bar; Home's quick actions follow the same rule (`dashboard_home.js`).
- The server also guards the pages: a Free member opening `/dashboard/widgets/schedule`, `/player-availability`, `/dashboard/widgets/assistant` or `/season-setup` is sent to `/pricing?feature=…` (`_paid_page_redirect` in `main.py`).

### Line-ups and guest matches (Oct 2026)
- **Line-ups first:** a match can't start scoring until both teams have a line-up of **2 to 11 players** (no player in both). Quick Score shows a "Team line-ups" step (tick club players, type the other team) before "Who's batting?". API: `POST /api/matches/{id}/lineups {club, opponent}` (scorers), stored in the `app_match_lineups` table; `GET /api/quick-score/{id}` returns `lineups` and `lineups_ready`. `POST /scorebook/setup` refuses to start without them (the older match-centre form still works when it lists at least 2 batters and 2 bowlers; those become the line-ups). Matches already being scored carry on.
- **All out** now means one fewer wicket than the batting line-up (e.g. 7 players → all out at 6 wickets; a full XI is still 10).
- **Guest matches (no sign-in):** `/score` for a signed-out visitor opens `static/quick_score_guest.html` ("Score" is in the public menu). Enter both team names, overs, ground and both line-ups → `POST /api/guest/matches` creates the match and returns a **6-character match code**. Scoring uses `/api/guest/matches/{id}` (state), `/setup`, `/ball` (POST and DELETE for undo) with the code in the `X-Guest-Code` header. "Have a match code?" (`GET /api/guest/resume?code=`) continues scoring on another phone.
- Guest matches are stored separately (`app_guest_matches`, JSON), so they never change club stats or member lists. They are scored on the day they are created only, show on the public Live page and at `/live/{id}` while being played (no code or private data is exposed), and the result is worked out automatically when the second innings ends.

### Simple menu and app tour (Oct 2026, soft launch)
- **Menu** (top bar on laptop, tab bar on phone): **Home · Matches · Score · Scorecards · Plans**. Files: `static/shared_header.html`, `SHARED_NAV_ITEMS` / `NAV_ALSO` / `renderSharedBottomNav` in `static/multipage.js` (the phone tab bar in `site_tools.js` copies the first five).
  - **Matches** = `/matches` (`matches_page` in `main.py`): Pro members, and players whose captain or club admin is on Pro, go to `/player-availability` (every upcoming game + Available / Maybe / Not available); everyone else goes to the public `/fixtures` list. The item stays highlighted on `/player-availability`, `/fixtures`, `/dashboard/widgets/schedule` and `/season-setup`.
  - **Scorecards** = `/scorecards` (Archives merged in): captains, club admins and site admins also see "📷 Upload a scorecard".
  - **Performances** is no longer in the menu (the page still works). **Profile, Clubs, Plans, the app tour and Admin** are in the account (initials) menu. The AI Assistant is the floating button.
- **App tour** (`static/app_tour.js`, loaded by `multipage.js`): 8 short steps that point at each menu item, the AI Assistant button and the account menu. It starts the first time a signed-in person opens Home (remembered in `localStorage` key `cricketClubAppTourSeen`), and again from the account menu "Take the app tour" or `/dashboard?tour=1`. Skip / Back / Next, arrow keys and Esc work.
- Sign-in now returns to the page you came from when the link has `?next=/path` (same site only); otherwise it opens `/clubs` as before.
- **First sign-in tour (Oct 16):** shown **once per account** (not per browser), on the first signed-in page after someone signs in for the first time. Saved in table `app_tour_seen` via `GET /api/tour` (`seen`, `can_score`, `name`) and `POST /api/tour/seen` (on Skip or "Let's go"). Steps say what to do: Welcome → Step 1 Pick your club (points at "Select club") → Step 2 Mark your availability → Step 3 Score a match / Step 4 Upload a paper scorecard (captains, club admins, site admins) or Step 3 Follow the live score / Step 4 See your scorecards (players) → AI Assistant → "You're all set ✅". Progress bar on every card. Only for first-time users: there is no "Take the app tour" item in the account menu any more (removed Oct 16); `?tour=1` still shows it for support. No tour on the sign-in page.

### AI Assistant answers (Gemini) (Oct 16 2026)
- Request: "train the AI so it can answer at least the basic questions, not only the related ones; why does it ask me to sign in when I am already signed in; display it completely on the right side".
- New `app/ai_chat.py`: sends the question to the free **Google Gemini** key already used for scorecard photos (`GEMINI_API_KEY`; optional `GEMINI_CHAT_MODEL`), or Claude (`ANTHROPIC_API_KEY`). The system prompt `APP_GUIDE` teaches it how the app works (menu, plans and prices, availability, scoring, uploads, RO = retired out, sign-in) and the answer rules: greetings and small talk, general cricket questions from its own knowledge, club questions **only** from the club data the app looked up (never invented numbers), no phone / email / age.
- `POST /api/muse` (`muse_chat` in `main.py`): tasks still go through the Confirm flow; questions are first looked up by the built-in data assistant (`answer_question`), then that result is passed to `ai_chat.answer()` as "Club data" together with today's date, club, speaker and next fixtures (`_muse_llm_context`) and the last 8 messages. If Gemini is busy or not set up, the built-in answer is shown as before. Ollama answers are kept as they are.
- `_muse_llm_call` (AI planning of tasks like "mark me available Saturday") also uses Gemini (JSON mode) when Ollama isn't running.
- Signed-in people on public pages (Live, Scorecards, Fixtures…) now talk to the full assistant (`muse_public.js` posts to `/api/muse` with the sign-in token): no more "Sign in for more" / "Sign in to score matches" while signed in; tasks needing Confirm show "Confirm on my dashboard".
- The assistant panel opens full height on the right side of the screen (440px wide, top to bottom); on phones it fills the screen (`static/muse.css`, end of file).
- **Built-in basic answers** (`basic_reply` in `app/ai_chat.py`, no AI needed): greetings ("hi", "hello", "how are you"), thanks / bye, "help" / "what can you do" (answered at once, with the person's first name); app how-tos (availability, scoring, scorecard upload, plans and prices, switch club, sign out, app tour) and common cricket terms (no ball, wide, LBW, retired out / RO, run out, strike rate, economy, maiden, duck, hat-trick, free hit, over, byes / leg byes) are tried with Gemini first and fall back to these answers when Gemini is busy or not set up. Add more by appending to `_BASIC`.
- The panel header says "Powered by Google Gemini" when the key is set (`chat_provider` in `GET /api/llm/status`), otherwise "Ask me anything or tell me what to do" (no more "AI model offline"); answers are labelled "AI Assistant" instead of "Heuristic fallback"; **bold** in answers is shown bold.
- **Typing feel (Oct 16):** after you send a message the assistant shows animated thinking dots for at least 1.2 seconds, then the reply types out (about 1.5 seconds, any length); links / Confirm buttons appear when the text is finished (`thinkAtLeast` / `typeOutLast` in `static/muse.js` and `static/muse_public.js`, `.muse-dots` in `muse.css`). Respects "reduce motion".

### Clean up and re-read all scorecards (Oct 20 2026)
- Request: "use all previous images and train it. Next we should clean up the data and re-extract all the previous scorecards to see if this is working correctly" (Amit). Choices made: delete uploads whose photo is not on this computer, keep one upload per photo, add the photos from `img/` that weren't in the app.
- **Admin Center → Clean up and re-read all with AI** (site admins): one button, runs in the background with a progress bar and the last cards read; the review queue refreshes when it's done. Options: clean up first (on by default) and skip cards already read by AI today (to continue after the free daily limit).
- Same thing from the terminal (app stopped): `python scripts\scorecards_reread_all.py --dry-run` (shows what would happen), `python scripts\scorecards_reread_all.py` (does it), `--skip-done` (continue later), `--no-cleanup` (re-read only).
- Steps: back up the database to `DB-Backup/before_reread_<date-time>/`; delete uploads without a photo in `app/uploads` or `img/`; find the same photo saved twice with a 16x16 picture fingerprint (catches HEIC/PNG copies and resized copies) and keep the oldest; add new `img/` photos (Heartlake, or the other club when the card names it); read every photo with the AI reader and run the smart checks, saving after each card; stop early if the AI stops answering; write a report to `scorecard_reports/reread_<date-time>.md`.
- Test the reader: `python scripts\scorecards_reread_all.py --samples` reads the 3 cards in `sample_scorecards/` and compares them with `answer_key.json`; results in `sample_scorecards/AI_TEST_RESULTS.md`.
- Training in git: names the reader learned from people's fixes are saved in `app/ai_learning.json` as well as the database table, and that file is committed, so Amit's copy, Azure and a fresh database all read with the same training. `known_names` in the file are extra player names the reader should know (e.g. Heshad, Sarabjeet from the Afghans card). The reading instructions themselves are in `app/ai_vision.py` (also in git). Gemini itself can't be retrained; the app trains it with these instructions and learned names on every read.

### Faster photo reading (Oct 20 2026)
- Request: "it takes so much time to read, can you not reduce it".
- One AI read on most cards: the second look (`_read_scorecard` in `app/ai_vision.py`) now only happens when the totals don't add up or two or more batters' runs don't match their ball-by-ball. A single small mismatch or a balls-count difference stays a note for the person checking. Before, most cards were read twice.
- Less thinking time: Gemini is asked with `thinkingConfig` (`thinkingLevel: low`, or a 512 budget on 2.5 models). If a model doesn't accept the setting it is asked again without it. `GEMINI_THINKING` in `.env` can be `low` (default), `high`, or `off`.
- The upload page shows live progress with a seconds counter (📤 Uploading → 🤖 Reading → Still reading after 45s).
- If Gemini can't be reached, the slower local reader (Tesseract / Ollama, about 1-2 minutes) is still used as the backup.

### Stats: basic for everyone, more for Pro (Oct 20 2026)
- Request: Stats should be seen by every player, with extra detail for Pro.
- **Stats** (`/dashboard/widgets/performance`, top menu) for every signed-in player: season picker, batting / bowling / fielding rankings, search a player, team roster and scoreboard. Ages are no longer shown in the roster.
- Only people who can manage players (site admin, or `manage_players` / `manage_club`) see **Invite player** and **Add player performance**. `main.py` sets `<body data-can-manage>` and CSS hides `[data-stats-manage]`; the APIs still check permissions.
- Pro members and site admins (`<body data-paid="1">`) get **Season by season**: each player's runs and wickets per season (last 4 seasons with numbers), best season and most improved player (`app/static/stats_page.js`, from `member_year_stats`). Free members see a Pro card with **Upgrade to Pro**.
- If the chosen season has no numbers yet but another season has, a note says "No numbers for 2026 yet" with a **See 2025** button.
- Numbers come from published scorecards and matches scored in the app; a fresh database shows empty rankings until scorecards are published.

### AI Assistant knows your club (Oct 20 2026)
- Request: "train AI assistant to do better".
- Every question answered by Gemini now gets a short club snapshot (`_assistant_club_snapshot` in `main.py`): club, season, today's date, who is asking, player names, upcoming matches, recent results, the latest published scorecards (scores, top scorer, best bowling), the top 5 run scorers and wicket takers for the last two seasons with numbers, and the asker's own season numbers. Names and cricket numbers only, never phone, email or age.
- Better instructions (`APP_GUIDE` in `app/ai_chat.py`): the new menu (Clubs and Stats), give real names and numbers straight away, "me / my" means the person asking, follow-ups use the earlier messages, ask one short question when unclear, reply in the person's language, bold names and numbers.
- Built-in answers (no AI needed): "where are the stats" and the new "switch club" (Clubs in the menu).

### Availability requests and match reminders (Oct 29 2026)
- Requested by Dhruvika: ask players about availability when a match is fixed, tell them about it, and remind them of their upcoming match. All of it arrives under the 🔔 bell (website and phone app); each message is sent once per match.
- **Match added** (Season setup / Fixtures): the whole club gets "📣 New match · are you available? vs GT · Sat Nov 7 · 10:00 AM" ("At Heart Lake Park. Tap to say Available, Maybe or Not available."), linking to the availability page.
- **Match already in the list**: once it is 7 days away it asks the same, if it hasn't been asked yet.
- **2 days before**: only players who haven't replied get their own reminder ("You haven't replied yet...").
- **The day before, from 6 PM**: "📅 Tomorrow: vs GT · Sat Nov 7 · 10:00 AM" with how many players are available so far.
- **Match day, from 7 AM**: "📅 Match today: vs GT · 10:00 AM" ("Good luck! Follow it live once scoring starts."), linking to the live page.
- **Date, time or ground changed**: everyone gets "Match changed · ..." and is asked to update their availability; the tomorrow / today reminders are sent again for the new date.
- Matches made with "Start a new match" (on the day) send none of these. Availability is a Pro feature, so during the launch (everyone on Pro) every club gets them; later, clubs on Pro.
- How it runs (`main.py`, "Availability requests and match reminders"): `_announce_new_fixture` / `_announce_fixture_change` when a match is added or edited, and `_run_match_reminders` every 5 minutes in the background and whenever someone opens the bell (so reminders still go out if Azure put the app to sleep). Table `app_fixture_reminders` (match, kind) makes sure each one is sent once, even with several workers. The bell shows 📅 for reminders (`muse.js`).
- Not yet: phone push notifications and email (they need an Expo account / an email service). Until then players see these when they open the app or website.

### Live page like a cricket score app (Oct 30 2026)

- Requirement 161. The public live page (`/live/{id}`) now looks like the big cricket score apps: white, compact, 14px text in the Roboto font (the one Cricbuzz uses).
- Top: LIVE / INNINGS BREAK / RESULT, the match line (date · time · type · overs · ground) and one row per team with a short badge (NZ, IND, HCC), overs, target (T:282) and score. The batting side (or the winner) is bold. Then the situation: "India need 104 runs in 28 balls", "Innings break · India need 282 runs to win" or the result.
- Three tabs (the tab is kept in the link, e.g. `#scorecard`):
  - Live: CRR, RRR and last 5 overs; the recent balls by over ("Ov 15 1 0 0 2 0 1 = 4"); the two batters (R B 4s 6s SR, * on strike); the bowler on now (*) and the one before (O M R W ECON); partnership and last wicket; the latest 6 balls of commentary. At the innings break and after the match: the top 2 batters and bowlers of each innings.
  - Scorecard: a bar per innings ("India Innings 178-4 (15.2 Ov)"), tap to open or close; full batting and bowling, extras, total, yet to bat, fall of wickets, C / VC / WK tags.
  - Commentary: every ball, latest first, with an "End of over" line (runs in the over and the score).
- Faster: it refreshes every 10 seconds while live and only redraws when something changed. The server now gzips its replies (`GZipMiddleware` in `main.py`), so a full live scorecard is about 8 KB instead of 88 KB on phone data, and the Score page and every other page load faster too.
- Files: `public_match.js`, `public_match.css` (versions 20261030a in `public_match.html`), `main.py`.
- Requirement 162. The whole app now uses the Roboto font (it used Inter, Sora, Anton, Space Mono, Source Serif 4, Outfit and Fraunces). Changed in every CSS file, the Google Fonts links in every page, the pop-ups built in JS (celebrations, tour, plan gate, zoom message) and the chart font in `main.py`. Changed CSS / JS files have version 20261030f so phones load the new look.
- Requirement 163. Same overs for both teams: when an innings is set up, its overs are copied to the other innings (if it hasn't started) and to the match (`_same_overs_both_innings` in `main.py`, club and guest matches). The "Start the chase" screen also shows the first innings' overs (`quick_score.js` 20261030g). Before, changing the overs on the first-innings screen (e.g. 2 -> 1) left the chase at the match's original 2 overs.
- Requirement 164. Live tab like Cricbuzz: grey "• LIVE"; one row per team with a two-colour team flag, short name (NZ, IND), "(15.2/20 ov, T:282)" and score; "India need 104 runs in 28 balls." with "CRR · RRR • Last 5 ov (RR)" under it and the match line in small grey; blue tabs; the balls newest on the left as square chips (• for a dot) with "15th · 4 RUNS" between overs; Win Probability (our own estimate from runs, balls and wickets left, with a blue / orange bar); BATTING and BOWLING tables with grey header bands across the page (striker marked *); partnership and last wicket. `public_match.js` / `.css` 20261030h.
- Requirement 165. Scorecard pages show "c & b Singh" when the catcher is the bowler (`howOutText` in `scorecard.js` 20261030i). Tested with a made-up 20-over Heartlake vs Toronto CC scorecard: everything else was read correctly.
- Requirement 167. Scorecard page (`/scorecards/{id}`) like the live page: white, Roboto, "RESULT", title 15px, one row per team with a two-colour flag and score (the losing side grey), the result in blue, then the match details in small grey; blue Scorecard / Original scorecard tabs; grey innings bars ("Heartlake Cricket Club Innings 224/9 (35 ov)"); BATTING / BOWLING tables at 15px with grey header bands, how out under the name, and 4s / 6s shown on phones too. `scorecard.js` / `scorecards.css` 20261030j (styles scoped to `.scorecard-detail-page`, the scorecards list is unchanged).
- Requirement 168. The uploaded scorecard page now uses the live page's own markup and styles (`public_match.css`): the same header (RESULT, team flags with short names, the result in blue, the match line), the same blue tab bar (Scorecard / Original scorecard), the same grey innings bars that open and close, the same Batter / Bowler tables (how out under the name, Extras and Total rows, ECON) and "Did not bat". `scorecard.js` / `scorecard.html` / `scorecards.css` 20261030k; the Admin Center snapshot uses the same look.

### A new match against the same team; Plans shown during the launch (Oct 29 2026)
- **Start a new match** (Score page): it used to reopen today's earlier match against the same team (e.g. a second GT game opened the first GT scorecard). Now an earlier match is reused only if no ball has been bowled in it yet; once it has started or finished, Start makes a fresh match (`quick_score_start` in `main.py`). Starting twice in the same minute says "A match against GT was started a moment ago. Open it from the list above."
- The match list shows each match's start time and state, newest first on the same day: **Score now** (not started), **LIVE · Continue** (in progress), **Finished · result · View** (opens the live scorecard). The form is now called "Start a new match".
- **Plans** (menu): in launch mode `/pricing` redirected Home. It now shows the plans with a green "Launch offer: every club gets Pro free" banner; Pro reads "Free during the launch · Later: $9 per month or $90 a year"; there are no payment buttons and the server refuses checkout while `CRICKETCLUBAPP_SUBSCRIPTIONS` is off (everyone stays on Pro, as Amit decided). The Plans menu links show again; only "Upgrade" links / buttons stay hidden. Turning payments on later is unchanged (set `CRICKETCLUBAPP_SUBSCRIPTIONS=on`).

### Captain, vice-captain and keeper (Oct 29 2026)
- Requested by Dhruvika: choose each team's captain, vice-captain and wicket keeper with the line-ups.
- Score page, "Team line-ups" (made simpler twice on Oct 29 at Dhruvika's request: first menus, then C / VC / WK buttons on every player were too cluttered): the player list is plain tick boxes again, and under each team there is **one line with three boxes: Captain · VC · WK** ("—" until chosen). Tap a box and a pop-up shows that team's chosen players; tap a name and it's set ("No captain" clears it). One person can't be captain and vice-captain at once (the other role moves off them); the keeper may also be captain or vice-captain; unticking or removing a player clears their role. A pasted WhatsApp list still fills them in by itself: "Ravi (c)", "Sam (vc)", "Dev (wk)", "Ravi*" (captain), "Dev†" (keeper); the markers are removed from the names. Guest matches: mark them in the line-up text the same way. All optional.
- Stored with the line-ups (`roles` in `app_match_lineups.lineups_json` / the guest match), checked by the server (`_clean_lineup_roles` in `main.py`: only names in that team's line-up; captain = vice-captain is refused), and included in `/api/quick-score/{id}`, `/api/guest/matches/{id}` and `/api/public/match/{id}` (names only).
- Shown as small **C**, **VC**, **WK** tags: on the openers / bowler buttons, the scoreboard batters, the next-batter and fielder buttons, and on the public scorecard (batting, bowling, yet to bat). For a stumping the wicket keeper is listed first.

### Balls are never lost (Oct 29 2026)
- Dhruvika's GT match: the database had only 15 balls of the chase (last at 11:32:08, GT 46/0), so the live page rightly said "GT need 29 from 15 balls". The balls scored after that never reached the server. Replaying the match from that point on the same code saved every ball and ended the match ("GT won by 10 wickets"), so the most likely cause was the app being restarted / unreachable while scoring. The Score page then showed "A ball wasn't saved" for a moment and **threw the ball away**, which at a ground with weak mobile signal would lose balls.
- Now (`quick_score.js`): a ball that can't be saved (no connection, server busy or restarting) stays in the queue and is retried automatically (2 s, then up to every 15 s, and as soon as the phone is back online). The red banner says "No connection · 3 balls waiting, will save automatically" and the score on screen keeps them. Waiting balls are also kept in the phone's storage (`qsQueue:<match>`), so closing or reloading the page doesn't lose them; they are saved when the page is opened again. Only a ball the server refuses (e.g. the innings is over) is dropped, with a message.
- Each new ball carries its own `client_id`, which becomes the ball's id on the server (`_client_ball_seen` in `main.py`, club and guest). If a ball was saved but the reply was lost, the retry is recognised and not saved twice.
- Tested: no signal (balls wait, then save in order), page closed with balls waiting (saved when reopened), the server stopped and restarted mid-match (nothing lost), a lost reply (saved once), the same ball sent twice (saved once); all earlier tests still pass (88 checks).

### GT test match check: new bowler every over, whole overs in the row (Oct 29 2026)
- Dhruvika's Heartlake vs GT test (local): every total, strike change and rate on the board was right. Two real problems found in the ball-by-ball data:
  - **Same bowler two overs in a row**: ball 2.1 of the 1st innings was saved with Player 1 bowling again, because closing "Who bowls next?" let scoring carry on. Now, when an over has ended, the next ball is only saved once a different bowler is picked: tapping a run re-opens "Who bowls next?" ("New over: pick the next bowler first.", `needsNewBowler` in `quick_score.js`). "Change bowler" mid-over (injury) still works.
  - **The "Last 12 balls" row started in the middle of an over** ("4 6 1 |" looked like a 3-ball over). The row now shows whole overs only, newest first, up to 12 balls (the over being bowled is always shown), e.g. "1 4 6 6 2 3 | 4 1 2"; the label says how many ("Last 9 balls"). Same on the public page.
- Tested on a copy of her GT match and with a new match: closing the pop-up and tapping a run asks again and saves nothing; the greyed-out bowler can't be picked; a wide + 4 after the change are the new bowler's; all earlier tests still pass.

### HURRAY! when a match is won, and no balls after an innings ends (Oct 29 2026)
- Dhruvika (Oct 29): "on winning do hurray!!". When the match ends, a big green-and-gold **🏆 HURRAY!** with the result ("Heartlake Cricket Club won by 18 runs"), lots of confetti and a long phone buzz, on the Score page and on the public live page (`ccCelebrateWin` in `celebrate.js`). A tie says "WHAT A FINISH!". It shows only at the moment the match is won, not when a finished match is opened later.
- Her test showed **RCB 28/11**: taps made right after the last wicket (before the page had caught up) were still saved. Now no new ball is accepted once an innings is over (all out, overs used up, or target passed): the Score page says "This innings is over. To change the last ball, tap Undo." and the server refuses it too (`_innings_is_over` in `main.py`, club and guest matches). Fixing a ball and Undo still work.
- Tested: rapid taps after the last wicket and after the winning hit are not saved; a ball sent straight to the server after all out is refused; HURRAY appears on both pages when the match is won and not when it is reopened; the full club match test (44 checks), guest / permissions and long-innings tests still pass.

### Last 12 balls in one row (Oct 29 2026)
- Amit (Oct 29, on Azure's older code the ball strip showed every ball of a 13-over innings in 9 rows): only the last 10-12 balls, in one row, the rest under "More".
- Score page (`quick_score.js`): "Last 12 balls" in one row that scrolls sideways, newest on the right (always in view), with a thin line between overs; tap a ball to fix it. **More ›** opens every over, newest first ("Over 13 · Bowl 1 · 14 runs, 1 wkt" and its balls); tapping a ball there fixes it too.
- Public page (`/live/{id}`): the same last-12 row on the scoreboard; the full list stays in "Ball by ball" below.
- The row can't widen the page (tested at 390 and 360 px with an 80-ball innings).

### Full test and fixes (Oct 29 2026)
Dhruvika asked for every detail to be checked before the Azure deploy. Tested in the cloud workspace on a copy of the real database, with the exact files from her folder, the package versions in `requirements.txt`, the server clock on GMT and **2 worker processes** (like Azure), at phone and laptop size:
- A full 2-over club match as a signed-in scorer (Start a match now -> 11 + 11 line-ups -> openers by tapping -> four, six, wide, no ball +4, byes, leg bye, bowled, caught, run out of the non-striker, next bowler, fix a ball, delete a ball, innings break, chase, win, undo after the win, win again), checking every total against our own count and the public page at each stage: 44 checks pass.
- A guest match to the end (all out), permissions (another club's admin can't score or change Heartlake's match; signed-out can't score), line-up rules (12 players, the same player in both teams), and 228 page loads (every page, signed out / super admin / another club's admin, phone and laptop): no script errors, no server errors, no page wider than a phone.
- The repo's tests: 32 pass (31 before); the 19 that fail also fail on the code from before this week (they expect test accounts that were deleted, e.g. player1 and testclub's captain, or older settings).

Bugs found and fixed:
- **Saving a ball took ~4 seconds** (club stats re-read every uploaded scorecard ~900 times per save) -> **~0.6 s**: `_build_materialized_club_stats` keeps the already-processed scorecard list (`_CanonicalArchiveList`) when it filters by club and year, and works out each player's milestones once per year instead of three times. All 48 tables come out identical.
- **Each ball sent 1.6 MB back to the phone** (the whole club dashboard, unused by /score). The Score page now sends `X-Lite-Response: 1` and gets `{"ok": true}` (27 bytes) from ball / setup / undo; the older "Advanced scoring" page still gets the dashboard.
- **Club match results were set too early** ("Club won" after the first ball of the chase) and **passing the target didn't end the innings**. See "How a scored match ends".
- **Undo didn't re-open a finished innings** in club matches (it did in guest matches).
- **"Who bowls next?" popped up over "Match complete"** when the winning run or last wicket came on the 6th ball of an over.
- **"This over" showed every ball of the innings** right after an over ended (`slice(-0)`); it now shows the over just finished.
- **No innings-break screen**: after the 1st innings the page jumped to "Start the chase", so a wrong last ball couldn't be undone. "First innings complete" (Start 2nd innings / Undo last ball) now shows first. The public page says "INNINGS BREAK · Afghans need 26 to win" instead of "NOT STARTED".
- **Guest scorers saw "Scoring is closed… opens on the match day" when they won**: now "Match complete", the result, both scores, View scorecard and Undo last ball.
- **Database export (backup download) copied only the main file**, missing saves still in the `-wal` file, and import swapped the file under a running database. Both now use SQLite's backup feature (`_sqlite_copy` in `main.py`). See "Database export and import".
- **The database had a stale index**: two sign-in sessions from Oct 15-16 were missing from the `app_auth_sessions` index (all data fine). The app now checks the database once when it starts and rebuilds any index that doesn't match its table (`_repair_indexes_once`); this changes no data. Tip: copy `cricketclubapp.db` only while the app is stopped (or use Admin Center's export), and keep it out of OneDrive / Google Drive syncing while the app runs.

### How a scored match ends (Oct 29 2026)
- For matches scored ball by ball, the result is written only when the match is over: the side batting second passes the target (its innings ends straight away) or its innings ends (all out / overs). Until then the result is "TBD", so the public page shows LIVE during the chase.
- Wording: "Afghans won by 3 wickets" (wickets left = line-up size - 1 - wickets lost, so 10 for an XI), "Heartlake Cricket Club won by 12 runs", or "Match tied" (`scorebook_result_text` in `cricket_store.py`, `_settle_scorebook_result` in `main.py`; guest matches use the same wording). Win / loss counts read this text as before.
- Undo after the end opens the innings again and clears the result. Matches entered from photos or by hand keep their results exactly as before.

### Database export and import (Oct 29 2026)
- Admin Center export downloads a complete snapshot made with SQLite's backup feature (including saves still in the `-wal` file); the temporary copy is deleted after the download.
- Import checks the uploaded file, keeps a complete backup of the current data (`cricketclubapp.backup-<time>.db`), loads the new data through SQLite and bumps the save counter so every worker reloads.

### Local time (Oct 29 2026)
- Azure runs on GMT/UTC, so "Start a match now" stamped Amit's 12:08 AM match as "4:08 AM", and anything using "today" could switch to the next day at 8 PM Toronto time.
- `main.py` now sets the app's time zone when it starts: `APP_TIMEZONE` (default `America/Toronto`), so `datetime.now()` and `date.today()` are Ontario time in every module. Stored timestamps (`now_iso()`) stay UTC with a "Z". On Windows the PC's own time zone is used as before.
- Matches created before this change keep the time they were saved with (e.g. 4:08 AM).

### Public scorecard (Oct 29 2026)
- Amit (Oct 29, Heartlake vs Afghans on Azure): the score wasn't shown completely (white text on white for status / target / runs / wickets, "--" for match situation and balls left, SR 0, ball numbers an over ahead: "5.3" for the 3rd ball of the 5th over), and every batting / bowling number was its own big box.
- `/live/{id}` (`public_match.html`, `public_match.js`, new `public_match.css`) is rebuilt, phone first, and everything is worked out from the ball-by-ball scorebook, so it always matches the Score page:
  - Scoreboard: LIVE / RESULT, both teams, batting side's score and overs (e.g. 65/2 (4.1/20 ov)), CRR, target and RRR, the other side's score, "Afghans yet to bat · 95 balls left" or "Tigers need 13 from 3 balls", the two batters (* on strike), the current bowler's figures, this over, the result when finished, and when it was last updated.
  - Scorecard with a tab per innings: one row per batter (R, B, 4s, 6s, SR, with "c Ali b Huron" / "b Shahid" / "batting *"), Extras (wd, nb, b, lb), Total with overs and run rate, Yet to bat (from the line-ups, now in `/api/public/match/{id}` as names only), Fall of wickets, and one row per bowler (O, M, R, W, Econ).
  - Ball by ball: latest first, with cricket ball numbers (4.1 = 1st ball of the 5th over) and short commentary ("Vraj to Ravi, FOUR!"), plus the scorer's own notes.
- Still refreshes every 15 seconds while live and celebrates fours, sixes, wickets, fifties and hundreds. The old "availability / selected XI / published performances" boxes are gone from this page (they belong to the club pages).
- Tested at phone size with an 11-a-side match (27 balls with a wide, a no ball, byes, two wickets) and a 1-over chase.

### Fresh data on every request: "Match not found." fix (Oct 29 2026)
- Amit on Azure (Oct 29): started a match against Afghans, filled both line-ups (11 each) and Save line-ups said "Match not found."; a later try (with 2 players) worked, so it looked like a player-count problem. It wasn't.
- Cause: every server process keeps the whole store in memory and only re-reads the database when the database file's time or size changes (`_database_signature` in `cricket_store.py`). The database runs in WAL mode, so a save first goes to the `cricketclubapp.db-wal` file and the main file often doesn't change. On Azure a second worker / instance therefore kept its old copy, without the new match, until something else changed the file. A save from such an old copy could also undo newer changes.
- Fix: every `save_store` adds 1 to a counter (table `app_store_version`, in the same transaction), and the in-memory copy is only used when the counter is unchanged. Reproduced with two processes sharing one database: before, the second process didn't see a new match; now it does. Saves still give the same data (48 tables compared).
- Line-ups: a 12th tick is refused ("11 players at most") and Save line-ups checks 2-11 per team before sending (the server checked already).
- Picking batters and bowlers from a list: done in "Easier live scoring" (name buttons from the line-ups). Azure still has the older text boxes until the new code is deployed.

### Easier live scoring (Oct 29 2026)
- Request (Amit, Oct 29): manual scoring was tedious; make live scoring really easy and interesting. Dhruvika picked: tap names instead of typing, fewer pop-ups, quicker line-ups, fixing mistakes, and celebrations.
- Tap, don't type: on "Who's batting?" the openers and the bowler are big name buttons from the line-ups (a name already picked is greyed out in the other box); "Someone else?" types a name that isn't in the line-up.
- One-tap pop-ups (no Save button; `openSheet` in `quick_score.js`): next bowler at the end of an over (shows the over's runs / wickets / "maiden!" and each bowler's figures; the bowler who just bowled is greyed out), byes / leg byes (1 2 3 4) and no balls (No runs, +1 ... +6). Wide still records 1 wide straight away.
- Wicket in 2-3 taps: How out (Bowled, Caught, LBW, Run out, Stumped, Hit wicket) -> fielder for caught / stumped / run out (the bowler is marked, "Don't know · skip"), for a run out also who is out and runs completed -> next batter (only players still to bat; "No more batters (all out)").
- Fix any ball: tap a ball in "This over" -> pick what really happened (runs, wides, no balls, byes, leg byes). The ball is replaced in place (`POST /api/matches/{id}/scorebook/ball` or `/api/guest/matches/{id}/ball` with the ball's `id`; `_apply_ball_edit` in `main.py` keeps its over, ball number and time; a fixed ball sends no new alerts; a finished innings opens again if the fix means it isn't finished). For the last ball there are also "It was a wicket" and "Delete this ball". Strike is worked out again when the last ball is fixed.
- Line-ups: "Select all" / "Clear" for the club's players, "Use Player 1-11" when the other team's names aren't known, and lists pasted from WhatsApp are cleaned ("1. Ravi (c)" -> "Ravi"; also for guest matches).
- Celebrations (`static/celebrate.js`): FOUR!, SIX!, WICKET!, FIFTY! and HUNDRED! pop up with confetti and a short phone buzz on the Score page, and on the public live page (`/live/{id}`), which now refreshes by itself every 15 seconds while the match is live (the first load never celebrates old balls). The banner never blocks taps; reduced-motion phones get a plain banner.
- Tested in the cloud workspace on a copy of the database at phone size (412 x 915): a full guest match (pasted line-up, picking openers, four, byes, caught, next bowler, fixing a 2 into a 4, no ball +4, run out of the non-striker) gave the right totals and strike, the public page celebrated a six from another phone, and fixing a club match ball kept its place.

### Saving only what changed (Oct 28 2026)
- Request (Amit + Dhruvika, Oct 28): the app should move to a cloud database later (Azure SQL / Turso etc.), and whichever one is chosen, a save must first write only the rows that changed.
- Before: every save (`save_store` in `app/cricket_store.py`) deleted and re-inserted every row of every table - about 3,600 row writes per save, even when one score changed. Fine for a local file, too slow and costly for a cloud database.
- Now: `_write_changes_only` runs the same table writers through `_DiffWriter`, which records what they would write, compares it with what is already in the database and writes only the differences: removed rows are deleted (child tables first), new or changed rows are inserted / updated (parent tables first), and an `UPDATE ... WHERE id=?` that changes nothing is skipped. `updated_at` on the stats and AI-index tables is ignored when comparing. Everything still runs in one transaction, so a failed save changes nothing.
- Tested on a copy of the real database (47 tables): first save 80 row writes, a one-player edit 3, adding a fixture 54 (the old way: 3,583-3,633 each time); after the same edits the database is identical to the old full rewrite in all 47 tables.
- Safety switch: if a writer does something the diff can't follow it falls back to the old full rewrite for that save; setting `CRICKETCLUBAPP_FULL_REWRITE=1` in `.env` / Azure forces the old way.
- Next (database plan): keep SQLite for the launch with an automatic backup copy, then move to a cloud database after launch; this change is the groundwork for that.

### Phone apps (Expo): one app for iPhone and Android (Oct 28 2026)
- Request (Dhruvika, Oct 28): "why not use react native with expo for both ios and android?" -> "go with react expo". Main reason: Expo's cloud (EAS Build) builds and submits the iPhone app from Windows, so no Mac is needed; one codebase for both phones, and later native screens are written once.
- New folder `mobile/` (Expo SDK 58, React Native 0.88, TypeScript): `App.tsx` shows the website in `react-native-webview` with the same native extras as before - bottom tabs Home / Live / Score / Scorecards / Upload, camera / photo library for scorecard photos (camera permission on Android, permission texts on iPhone), pull to refresh on iPhone (on Android tap the open tab again), Android back button through the pages, "No internet" screen, outside links (WhatsApp, phone, email, other sites) open in their own apps, `cricketcanclubs://` links open the page. User agent `CricketCanClubsApp/1.0 (Expo)`, so the website hides its own bottom bar and uses the in-app tour. Website address in `mobile/src/config.ts`.
- `app.json`: name CricketCanClubs, ids `com.cricketclubapp` (same as before), icon / adaptive icon / splash (green, stumps and ball - placeholder until there's a logo), iPhone only (no iPad), portrait. `eas.json`: `preview` (Android .apk for testers), `production` (store builds).
- Checked in the cloud workspace: TypeScript passes, the Android bundle builds (`expo export`), and `expo prebuild` produces the expected Android manifest (camera permission, scheme) and iPhone Info.plist. Not yet run on a phone.
- The Swift (`ios/`) and Kotlin (`android/`) apps from Oct 26 are replaced; they stay in the repo for reference only. How to try, build and submit: `mobile/README.md` and `MD/PHONE_APPS.md`.

### App tour in the phone apps and for visitors; Privacy policy and Delete my account (Oct 27 2026)
- Request (Dhruvika, Oct 27): "do we have app tour for first time visitors?" -> yes for members after their first sign-in; add one for visitors, and make it work inside the apps. Privacy policy and account deletion are required by Google Play and the App Store.
- `app_tour.js`: inside the iPhone / Android app (user agent `CricketCanClubsApp`) the steps that point at Score, Upload, Live and Scorecards say "tap Score in the tabs at the bottom" and the card sits just above the app's native tabs (the website's own bottom bar is hidden there). First-time visitors who are not signed in get a 3-step welcome on `/live` (what CricketCanClubs is, Sign in / Register your club, score a quick match without an account), once per browser (`cricketClubAppVisitorTourSeen`); `?tour=1` shows it again. `public_header.js` loads it for signed-out visitors on `/` and `/live`.
- Privacy policy: `/privacy` (`privacy.html`, public menu -> More -> Privacy): what is collected (account, optional profile, cricket activity, scorecard photos, AI messages), what is public (names and cricket stats) and never public (phone, email, age), services used (Azure hosting, Google Gemini for scorecard reading and the assistant), deletion, children, contact. The contact is `SUPPORT_EMAIL` from `.env` / Azure settings, else "your club admin".
- Delete my account: Profile page card (`account_delete.js`) -> type DELETE -> `POST /api/account/delete` deletes the sign-in account and everything linked by user id (sessions, settings, tour) and signs out everywhere; published scorecards and the club's player record stay as match history. Site admin accounts can't delete themselves. The admin delete (`DELETE /api/admin/users/{id}`) now shares `_delete_app_user`.

### Amit's Azure check: own club on Home, one menu, next match (Oct 27 2026)
- Request (Amit, Oct 26, after deploying to Azure): (1) Heartlake's Home showed other clubs' scorecards under Latest scorecards; (2) menus are not consistent; (3) Next match showed an old, past game - it should show nothing when no game is scheduled; (4) Plans are not showing.
- (1) `dashboard_home.js`: Home asks `/api/auth/me` for the member's club (the old code read the club from localStorage, but it is kept in sessionStorage, so it was always empty and every club's cards showed). Latest scorecards, Live, Results and Coming up now show only the member's club: cards owned by the club, or where the club is one of the teams ("Heartlake Cricket Club" = "HEARTLAKE CC" = "Heart Lake"). A superadmin with no club still sees all.
- (2) One menu when signed in: public pages (Live, Fixtures, Scorecards, Rankings, a scorecard, Upload) showed the public menu (Live scores · Fixtures · Scorecards · Rankings · My dashboard) even when signed in. Now `public_header.js` checks the sign-in first and a signed-in member gets the same signed-in menu, bottom bar and assistant as on Home (it loads `multipage.js`). Signed out, the public menu is unchanged. The signed-in menu (`shared_header.html`) now also has Live scores and Rankings, so nothing is lost.
- (3) Next match: `app.js` shows only a match still to be played (today or later, not completed) in the "Next" label, the Next Match panel and the upcoming list; with none it says "No upcoming match scheduled" with an Add a fixture button (it used to show the last played game). `cricket_store.py`: `landing_upcoming_matches` no longer falls back to completed matches.
- (4) Plans: hidden on purpose - Amit's launch decision (Oct 24) is everyone on Pro with no subscriptions, so Plans / Upgrade are hidden and /pricing goes to Home. Turn them back on with `CRICKETCLUBAPP_SUBSCRIPTIONS=on`.
- Asset versions bumped to `?v=20261027a` so phones and browsers load the new files.

### Phone apps: Android + iPhone for the Diwali launch (Oct 26 2026)
- Request (Amit, Oct 26: "Can we build the app by Diwali? Native iOS and Android?"): launch website + iPhone + Android together on Nov 8. A full native rebuild of every screen takes months, so the apps show the website inside a native app (web, iPhone and Android stay in lockstep) and native screens follow after launch.
- Android (`android/`, Kotlin + Compose): native bottom tabs Home / Live / Score / Scorecards / Upload, camera or gallery for scorecard photos (FileProvider, no camera permission needed), pull to refresh, back button through pages, "No internet" screen with Try again, WhatsApp / phone / email / other sites open in their own apps, splash screen, app icon, name CricketCanClubs. targetSdk 36 (Play's rule for new apps), AGP 8.11.1, Gradle 8.13, Kotlin 2.1.21.
- iPhone (`ios/`, SwiftUI + WKWebView): the same tabs and features; camera / photo library permission texts; iPhone only, portrait; app icon and launch colour in `Assets.xcassets` (now part of the Xcode project); team AT2629ZM2V.
- Website: inside the apps (user agent contains `CricketCanClubsApp`) the website hides its own bottom bar (`multipage.js`), so there is only one.
- Website address: Android `BASE_URL` in `android/app/build.gradle.kts`, iPhone `defaultBaseURL` in `ios/Sources/AppConfig.swift` (both `https://cricketcanclubs-web.azurewebsites.net`).
- Build, test and store steps, dates, Google Play's 12-testers / 14-days rule: `MD/PHONE_APPS.md`. Store icon and feature graphic: `store_assets/`. The icon is a placeholder until there is a club logo.

### Worked examples: training the reader with checked cards (Oct 27 2026)
- Request (Dhruvika, Oct 26): "train it to do better than this, train it properly this time", after only 13 of 32 re-read cards were right and a published card (IMG_1975) turned out to have bowlers credited one row off.
- What was wrong, found by checking photos digit by digit: (1) HOW OUT / BOWLER read one row too low for some batters; (2) a circled shirt number in the BOWLER column ("(12)") not matched to the bowler wearing it; (3) plain "W" in bowling boxes counted as wickets when on these cards it means a wide; (4) bowlers' overs guessed instead of counting the boxes; (5) extras tallies ("11111" = 5) flagged as wrong even when the total added up.
- **Worked examples** (`app/ai_examples/`, committed to git so local and Azure read the same way): 3 cards checked by a person with their correct JSON and short lessons - `example_1` (IMG_1975, Police Community book: rows, shirt numbers, circled running runs, W = wide) and `example_2` (IMG_5094, Heartlake book: TOTAL column, tallies, over-by-over total, bowler written above the heading). Every Gemini / Claude read sends them first as "here is a card and how to read it" (few-shot), then the new photo. The photo being read is never its own example. `AI_WORKED_EXAMPLES` in `.env` sets how many (default 3, 0 = off). The Ollama backup doesn't use them (too slow on a PC).
- **Worked example 3** (Oct 30, requirement 166): a printed 20-over card, Heartlake 158/6 beat Toronto CC 138/7 (`example_3.png` / `.json`, every number adds up). Teaches printed tables, "c & b", run out with a fielder and no bowler, and "Did not bat".
- **Caught and bowled**: "c & b Singh", "c&b", "ct & b", "C+B", "caught & bowled", or a catch where the catcher is the bowler, is saved as type "caught and bowled" with one name (`is_caught_and_bowled` in `ai_vision.py`), and every scorecard shows it as "c & b Singh" (`_scorecard_dismissal` in `main.py`, `howOutText` in `scorecard.js`). "hit wicket" now shows the bowler too.
- **Cross-checks** (`cross_checks` in `ai_vision.py`): the card is checked against itself - bowlers' runs = total minus byes and leg byes; bowlers' overs = innings overs (a whole over out is allowed: paper books often leave a bowler off); each bowler's wickets = batters out to him in How out; every How out bowler is in the bowling list; 4s x 4 + 6s x 6 is not more than the runs; wickets = batters out. Any problem makes the reader look at the photo again with the problem spelled out (the same second look as "totals don't add up"), and anything still wrong is shown to the person to check. Nothing is checked when the numbers aren't on the card, so handwritten books with an empty bowling summary get no false alarms (tested on examples 1 and 2). The prompt also tells the AI to do these checks itself before answering. Tests: `tests/test_ai_reader_checks.py` (no AI key needed).
- Add a checked card as an example: fix it with Edit until every number matches the photo, then `python scripts\add_ai_example.py <upload id> "lesson"` and commit `app/ai_examples/`. Keep 2-3: each example is sent with every read.
- Better instructions (PROMPT): read HOW OUT / BOWLER / TOTAL on the batter's own row; circled number = shirt number; bowling boxes: overs = boxes used, circled corner number = running runs, LB / BOW / CT / ST = wickets, plain W often a wide; extras boxes are tallies; null instead of a guess.
- Totals check (`reconcile_totals`): when batters + extras don't make the total, the reader tries what the card itself offers (a batter's ball-by-ball sum, or the extras boxes read as tallies). Only if exactly ONE such change makes it add up is it used, with a note "used X. Check it."; otherwise the card waits for a person.
- Fewer false alarms: "Check the extras" is not shown when the total adds up or the tallies make the extras total. New note when the bowlers' wickets are more than the batters out to a bowler, or their overs more than the innings (`bowling_notes`).
- Reader version `2026-10-27` (so "Skip cards already read" reads every card again with the training).

### How the AI reader learns (Oct 19 2026)
- Request: "train AI to read properly", after the Heartlake vs Afghans card was read with Meshad instead of Heshad, Keshav 4(17) as 12 balls, and the year 2026 as 2020.
- Better instructions (`app/ai_vision.py` PROMPT): the TOTAL column is RUNS(BALLS), so "4(17)" = 4 runs off 17 balls; the AI also counts the balls in each batter's ball-by-ball scribbles (`ball_count`); the year is read digit by digit.
- Extra help for each club (`_prompt`): the photo date (the match is on or before it, usually the same year), names this club corrected before, and other players seen on the club's published scorecards (`_ai_known_names`: roster, aliases, approved cards).
- Learns from fixes: when someone saves a card with **Edit** / "Type in the scorecard" (`POST /api/scorecards/{id}/manual`) or the Admin Center JSON box (`POST /api/admin/archive/{id}/review`), names the AI misread and the person changed (same innings and row, similar spelling) are saved per club in the `app_ai_corrections` table (`_learn_ai_corrections`). The save message says "The AI will remember: Heshad".
- After every read (`_apply_learning`): corrected names are swapped in automatically; names very close to a known player (80% match) are changed to that player; a year far from the photo's year is fixed when the same day/month is just before the photo date; a date after the photo is flagged. Each change is listed in the review notes so it can be checked.
- No typing needed (Oct 19, request: "I don't want to edit manually, train the model to run it properly"): the AI is told to read names letter by letter (H/M, K/R, U/V look alike in capitals), and to work out bowling overs / runs / wickets from the BOWLING ANALYSIS boxes when the BOWLING SUMMARY is empty. After the read, each bowler's wickets are filled from the batting card's BOWLER column, a batter with no balls gets the ball-by-ball count, and the date read sets the season (2026 Season).
- Photo date (`_photo_date`): a date in the phone's file name ("WhatsApp Image 2026-10-18 …", "IMG_20261018"), else the camera date, else the upload time for photos uploaded in the app. A computer's file-modified time is not used, so old photos copied later keep their real year.
- Balls check: if a batter's balls and the ball-by-ball count differ by more than 2, the AI reads the photo a second time, and a note "Check Keshav's balls…" stays if it still differs.

### Re-extract uses the AI reader (Oct 16 2026)
- Request (Amit, Oct 15): "Updated the admin center to re-process the images. Please check as the scorecards are not getting extracted. This needs to be fixed as this is the main feature."
- Cause: **Re-extract** in the Admin Center (`POST /api/archive/{id}/extract`) only ran the basic Tesseract reader, which can't read handwriting, so the review JSON came back empty (`null` runs, `did_not_bat`). The AI reader was only used on new uploads and the "Read with AI" button.
- Now Re-extract reads the photo with the AI vision model first (Gemini / Claude / Ollama, `_scorecard_ai_read`, HEIC photos converted to JPEG), runs the smart checks, and only falls back to Tesseract when AI is off or fails; the message says which reader was used and why.
- `_scorecard_ai_read` now also stores the AI result as `review_source_json` / `review_template_json` / `extraction_template`, so the Admin Center JSON box, the snapshot and the public card all show the AI reading instead of an older OCR template.
- Card builder fix (`_scorecard_from_archive`): when the template lists batters for both innings, untagged imported player rows are no longer added to the 1st innings (the other team's batters used to show up twice).
- Admin Center feedback (`admin_center.js`, Oct 17): while it works the card shows "⏳ Reading the photo with AI…" and the button says "Reading…"; afterwards the server message ("Read by AI (gemini)…" or why it fell back) appears at the top of that card. The button used to fire twice (inline `onclick` + list click listener) and only showed its message in the banner at the very top of the page; it now runs once per card.
- Needs a free `GEMINI_API_KEY` in `.env` on each computer that runs the app (see "Reading handwritten scorecards automatically").
- Old photos: Amit's database refers to photos by file name; copy them from `img/` into `app/uploads/` (same names) so Re-extract can find them.

### Plans: what each group can use (Oct 16 2026)
- Request (sticky notes: "registered can use AI / score according to the subscription", "AI for paid or AI for 1 match", "not regular: no login but can still use scoring manually"): "restrict the features before sign in and also for less paid plan users".

| | Not signed in | Free | Pro |
|---|---|---|---|
| Live scores, fixtures, scorecards, rankings, clubs | ✅ | ✅ | ✅ |
| Score a match by hand (big buttons, local voice shorthand) | ✅ guest match with code | ✅ | ✅ |
| AI Assistant | ❌ button says "AI Assistant · Sign in" and opens /signin | 1 free AI try | ✅ |
| AI Scorer | ❌ not shown on guest matches | 1 free AI try | ✅ |
| Upload a scorecard photo | ❌ (captains / club admins only) | 2 a month | Unlimited |
| AI reading of the photo | ❌ | 1 free AI try, then basic reader + type in | ✅ every upload |
| Availability, Playing XI, alerts, analysis, more than one club | ❌ | ❌ (players in a Pro club get availability) | ✅ |

- **One free AI try** (`AI_TRIAL_FEATURES` in `app/subscriptions.py` now includes `ai_extraction`): a Free user's first use of AI, either on a match (AI Assistant / AI Scorer) or reading one scorecard photo (`scorecard:<upload id>`), becomes their free AI try; after that, AI on anything else needs Pro.
- **Server checks** (`app/main.py`): `POST /api/public/muse` answers only signed-in people (others get "The AI Assistant is for members. Sign in…"); the upload runs AI reading only when `_ai_allowed(..., "ai_extraction", ...)`; `POST /api/scorecards/{id}/ai-read` returns 402 with the upgrade message; the preview returns `ai_available` / `ai_locked`; `GET /api/scorecards/reader` tells the upload page which reader this person gets.
- **Screens:** `muse_public.js` (🔒 "AI Assistant · Sign in", no button on sign-in/register pages), `quick_score.js` (no 🤖 AI Scorer on guest matches), `scorecard.js` ("🤖 Read with AI 🔒 Pro" links to /pricing), `scorecard_upload.js` (sends the sign-in token so the note is right). Site admins keep everything.

### Public menu (Oct 16 2026)
- Request: "right now everything is shown before sign in, do you think all of this should be shown" → keep it short, but Score, Clubs etc. must still be reachable before sign-in.
- `static/public_header.html` (signed-out header on Live, Fixtures, Scorecards, Rankings, Score, Clubs, Plans, Sign in, Register): the row shows **LIVE · Fixtures · Scorecards · Rankings · Sign In** and a **More ▾** button on every screen size. More holds **Score · Clubs · Plans · Register · Dark mode** (links marked `nav-always-more`, opened by `setupMoreMenu` in `public_header.js`). All those pages still work without signing in.
- Phones: the ☰ drawer lists every link; the bottom tab bar (`renderTabbar` in `site_tools.js`, first 5 non-account links) is LIVE · Fixtures · Scorecards · Rankings · Score.
- CSS: end of `static/live.css` ("Public menu"). Signed-in visitors on these pages still see "My dashboard" in place of Sign In and "Sign out" (in More) in place of Register.
- Oct 16 follow-up: the bar shows **CC CricketCanClubs** (name next to the logo from 1180px wide); the first tab is **🔴 Live scores** (was "LIVE"); **More** sits at the right end next to search / dark mode and no longer repeats Dark mode; when signed in, **Sign out** is its own button at the far right (and in the phone ☰ menu), not inside More.

### Simple Live page (Oct 16 2026)
- Request: "on the home page remove not needed things, make it simple".
- `/live` (`static/live.html`, `static/home.js`) now has just: the welcome banner (Sign in · Register your club, or "Go to my dashboard" when signed in, plus "Or score a quick match without signing in →") with the featured live / latest match, then **Recent results** and **Coming up**.
- Removed: the scrolling score strip (All / Live / Results / Upcoming), the Clubs / Fixtures / Scorecards counters, the Latest scorecards grid (on /scorecards) and the "Run your club" banner. `home.js` skips the strip and scorecards code when those elements are missing.

### First page (Oct 16 2026)
- Request: "when a new user logs in, what page should be shown first".
- **Opening the app** (`/`, `root` in `main.py`): signed out → `/live` (live scores anyone can see, with Sign in in the menu); signed in → `/dashboard` (Home).
- **After signing in** (`signin.js`): `?next=` page if given; otherwise **Home** when the account already has a club (`current_club_id` / `primary_club_id`), or **Clubs** to pick one when it has none.
- **First sign-in tour** follows: the "Pick your club" step is only shown on `/clubs` or when the account has no club (`has_club` from `GET /api/tour`); the remaining to-do steps are numbered automatically.

### Simple sign-in page (Oct 16 2026)
- Request: "make the sign-in page more simple, remove unnecessary stuff". Then: "give app tour after sign in only for the first time, like showing the thing to be done".
- `/signin` is now one centred card: **Sign in** · Mobile or email · Password (placeholder "No password? Leave empty") · Sign in · Create an account. The League leaders panel (top batters / bowlers / clubs) was removed from the page and from `signin.js` (`GET /api/public/signin-stats` still exists, unused). Leaders are still on `/rankings`.
- The **Player name** box is hidden. It only appears when sign-in without a password can't find the person by mobile/email alone ("We couldn't find you yet. Add your name as your club saved it…"), or when the browser fills it in.
- Files: `static/signin.html`, `static/signin.js`, `static/signin.css` (`.signin-simple`, `.si-field[hidden]`).

### Scorecard uploads: checks, review and duplicates (Oct 2026)
- **Who uploads:** captains, club admins and site admins (new permission `score_matches`, also used for live scoring, line-ups and the AI Scorer; captains and club admins only for their own club's matches, `_require_match_scorer` in `main.py`). Players can't upload; they're asked to send the photo to their captain. Approving other people's uploads stays with the site admin (`manage_scorecards`).
- **Upload page** `/scorecards/upload` (`static/scorecard_upload.html` / `.js`): take or choose a photo → `POST /api/scorecards/upload` → the page opens the **complete digital scorecard** at `/scorecards/{id}?preview=1` with the check results.
- **Smart checks** (`app/scorecard_checks.py`, run by `_scorecard_upload_checks`):
  - same photo file (exact hash) → refused;
  - same photo saved again, resized or re-compressed (8×8 "average hash" fingerprint, ≤ 5 bits different) → refused, naming the earlier upload;
  - same date, same two teams and same two scores as another upload → flagged as a possible duplicate;
  - **AI duplicate check (Oct 16):** when an AI is set up (Gemini key in `.env`, else Claude, else Ollama) and the simple checks found nothing, the AI is asked "same match?" about up to 4 other uploads from the same day, or with a shared team and a total within 10 runs (`scorecard_checks.ai_candidates` + `card_summary`, `ai_vision.same_match`) → flagged "AI thinks it's the same match (…)" for the site admin;
  - "not proper": photo couldn't be read, no date, both teams or both totals missing, more than 10 wickets, more overs than the limit, batters' runs + extras ≠ total, more batters out than wickets.
- **What happens next:**
  - No problems → status `Pending review`; the scorer checks the digital scorecard and taps **"✓ Looks right, publish"** (`POST /api/scorecards/{id}/publish`) → `Approved`, shown on Scorecards, club notified. (Uploads whose extraction already has both innings are approved automatically, as before.)
  - Problems → status **`Needs admin review`**, every site admin gets a notification ("Scorecard needs review"), and if the scorecard has errors the club's players get "Scorecard being checked".
  - **"Something's wrong"** on the preview (`POST /api/scorecards/{id}/report {note}`) sends it back to the site admins with the note, hides it until checked and tells the players.
  - `GET /api/scorecards/{id}/preview` (uploader, own club's scorers, site admins) returns the digital scorecard, status, flags and possible duplicates.
- **Typing it in:** handwritten photos usually can't be read without a vision model. Then the preview shows **"✏️ Type in the scorecard"**: a form for the teams, date, totals, batters and bowlers (the photo opens in a new tab beside it). Saving runs the same checks. With an Ollama vision model installed (`ollama pull qwen2.5vl:7b`) the photo is read automatically and the form is only needed for corrections.
- **Site admin page `/admin/scorecards`** (`static/scorecard_admin.html` / `.js`, also in the account menu as "Scorecard checks"): uploads waiting for review with their reasons, **Approve / Reject** (`POST /api/admin/scorecards/{id}/decision {decision, note}`; the uploader is told), and the **duplicate report** (`GET /api/admin/scorecards/checks`) grouping uploads by same file, same photo, same phone file name (`IMG_3261.heic` / `.png` / `.jpg`) or same date + teams + scores. "Hide ticked duplicates" (`POST /api/admin/scorecards/duplicates/hide {ids}`) sets them to `Duplicate`: nothing is deleted, but `Duplicate` and `Rejected` uploads drop out of scorecards, stats, lists and queues (`HIDDEN_ARCHIVE_STATUSES` in `cricket_store.py`). Older uploads get their photo fingerprint the first time the page is opened.
- Upload details (`original_file_name`, `image_fingerprint`, uploader, flags, possible duplicates, review note) are stored in the new `archives.extra_json` column (added automatically). `Needs admin review`, `Duplicate` and `Rejected` are no longer turned into `Approved` when the store loads.
- On the user's current database the report finds 8 groups / 13 duplicate uploads (the same phone photos saved as .heic, .png and .jpg).

- **🤖 Ask AI to find more duplicates** (site admin, `/admin/scorecards`, `POST /api/admin/scorecards/duplicates/ai-scan`): asks the AI about up to 25 likely pairs the simple checks missed (same game read slightly differently) and adds them to the duplicate list, already ticked; then "Hide ticked duplicates" as before. Request: sticky note "fix the duplicate SC, use smart detection through AI or Ollama".

### How to test (Oct 2026, soft launch)
1. Restart the app (new permission and table are added on start).
2. **Plans:** `/pricing` shows Free and Pro. Pro shows **$9 per month** with Monthly selected; tap **Yearly** → **$90 per year**, "That's $7.50 a month. Save $18 a year (2 months free)". Site admin "Manage plans" offers Pro / Free; old Super/Premium/trial users show as Pro.
3. **One free AI match:** set a captain to Free. In Quick Score on today's match, the 🤖 AI Scorer says "try AI on one match for free"; use it → that match becomes the free AI match. On a second match the AI Scorer and AI Assistant tasks show "Your free AI match is used" with a link to Pro; the first match still works.
4. **Menu + tour:** sign in on a phone (390 px) and on a laptop: the menu is Home · Matches · Score · Scorecards · Plans, the tour starts once on Home, and "Take the app tour" in the account menu replays it. Matches opens availability for Pro, `/fixtures` for Free.
5. **Upload:** as a captain open Scorecards → "📷 Upload a scorecard" → choose a photo → the digital scorecard opens with the checks. Upload the same photo again (or a resized copy) → refused. Tap "Something's wrong" → site admins get a notification and players see "Scorecard being checked".
6. **Admin:** as the site admin open account menu → Scorecard checks → Approve / Reject an upload; tick duplicates and "Hide ticked duplicates" → the duplicate groups go and stats count each match once.
7. A player (no captain role) opening `/scorecards/upload` is told to ask their captain; scoring another club's match as a captain is refused.

### Reading handwritten scorecards automatically (Oct 2026)
- Paper scorecards are handwritten, and the free local reader (Tesseract) can't read handwriting. The app reads them with an AI vision model instead (`app/ai_vision.py`). The first one configured is used:
  1. **Google Gemini, free** (recommended): get a key at https://aistudio.google.com/apikey (Google account, no card) and put `GEMINI_API_KEY=...` in `.env`. Free tier has a daily limit (plenty for club use); when it's reached the app says so and the scorecard can be read the next day or typed in. Note: Google may use free-tier requests to improve its products. Optional `GEMINI_VISION_MODEL` (default `gemini-3.8-flash`, falls back to other free Flash models).
  2. **Anthropic Claude, paid** (a few cents a photo): `ANTHROPIC_API_KEY=...`, optional `ANTHROPIC_VISION_MODEL` (default `claude-sonnet-5-5`).
  3. **Ollama on this computer, free and offline (the club's choice, Oct 2026):** install Ollama (0.12.7 or newer) from https://ollama.com/download, then run `ollama pull qwen3-vl:8b` (6.1 GB; on a PC with less than 16 GB memory use `qwen3-vl:4b`, 3.3 GB). Keep the Ollama app running; the app finds the model by itself (`ai_vision.ollama_model()`, optional `OLLAMA_VISION_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_VISION_TIMEOUT` seconds, default 600). Without a graphics card a photo takes a few minutes. Same prompt and checks as the online readers; less accurate on messy handwriting, so always compare with the photo.
  4. Otherwise: Tesseract plus the **Type in the scorecard** form.
- `.env` lives in the project folder next to `app` (copy `.env.example`), is in `.gitignore`, and is read when the app starts (restart after editing).
- **What happens:** every new upload is sent to the model with the club's player list; it returns the scorecard as the app's template JSON (teams, date, each batter's runs and how out, extras, total, bowlers), which goes through the normal import and checks. The scorer compares it with the photo and taps Publish; anything that doesn't add up goes to the site admin. AI-read and typed-in scorecards are never published automatically.
- **Older uploads:** open the upload (Scorecard checks → Open digital scorecard) and tap **🤖 Read with AI** (`POST /api/scorecards/{id}/ai-read`).

### Home: live and past matches (Oct 2026)
- The signed-in Home "Matches" section opens on **Overview** with three clear rows: **🔴 Live now** (with "Score a match"), **🏁 Recent results** (with "All scorecards") and **📅 Coming up**. The Live / Results / Upcoming tabs still filter. Played games without a written result show "Full time" instead of "Result not recorded".
- Home quick actions start with **🎯 Score a match**; "Update availability" shows only when the member can use it, and Free members get "⭐ See plans". The AI assistant card lists the tasks it can do.
- Phone fix: wide tables and toolbar forms on Clubs and Admin center no longer push the page sideways (`app_polish.css`).

### How to test (Oct 2026, round 2)
1. Free member: set a user to Free on `/pricing` (Manage plans), sign in as them: the menu shows Home, Scoring, Archives, Scorecards, Clubs, Performances, Profile, Plans; opening `/player-availability` goes to Plans. A paid member sees the full menu.
2. Signed in, Quick Score → start a match → the Team line-ups step appears; saving with 1 player shows "needs at least 2 players"; with 2–11 per side it moves to "Who's batting?".
3. Signed out, open `/score` → fill both teams and line-ups → Create → note the code banner → score a few balls → open `/live` in another browser: the guest match is listed.
4. Home (signed in): check Live now / Recent results / Coming up.

### Past matches are locked (Oct 2026)
- A match whose date is before today (Toronto time, `_current_local_date`) is read-only for everyone: scores (`/scorecard`, `/performances`, `/commentary`, ball-by-ball), availability (`/api/matches/{id}/availability`, `/api/player/availability`), the playing XI (`/lineup`) and AI Assistant score/availability tasks all answer **403 "This match was on … Past matches are locked"** (`_require_not_past` in `main.py`). Old scores are added by uploading the scorecard photo to Archives for admin review.
- The match centre disables the score, performance and commentary forms for a past match and shows a note (`applyPastMatchLock` in `app.js`).
- Past games are no longer shown as upcoming: the Availability page and `/api/player/availability-data` list only today's and future fixtures; the Fixtures widget shows upcoming fixtures only (past ones are folded under "Past fixtures" in the fixture manager); the public and signed-in Fixtures pages hide past games that were never played or scored (played games stay as results); Home strips never show an earlier day's game as Live or Upcoming, and the public live list skips games from earlier days.
- Admins can still edit or delete a past fixture's details (date, opponent) from the fixture manager.

### How to test (Oct 2026)
1. Restart the app. Open Availability: only today's and future fixtures are listed. Open Fixtures: no past "Scheduled" games; the fixture manager shows "Past fixtures (N)" folded.
2. Open a past match in the match centre: the score form is disabled with "This match has been played…". Try saving availability for a past game from another page: you get "Past matches are locked".
3. Tap **✨ AI Assistant** and try: "Add a match vs Old Boys XI on Saturday at 2pm" → Confirm; "Ask everyone for availability"; "Mark me available for the next match"; "Who is available for the next match?"; "Pick the best XI for the next match"; "We are 85/3 after 12 overs" (needs a match today, e.g. from Quick Score). Each shows a plan with Confirm / Cancel.
4. Ask a question ("How is Amit S doing?"): it is answered by the LLM (the header says which model) or the built-in data assistant when Ollama is off.

### How to test (September 2026 features)
1. Restart the app: `python app\main.py` (stop any old copy first: `netstat -ano | findstr :8090`, then `taskkill /PID <id> /F`).
2. `/scorecards` → pick 10/19/2024 → open the card → check both tabs.
3. `/live` (signed out) and `/dashboard` (signed in) → check the match strip, latest scorecards and the AI Assistant card.
4. `/score` → "Start a match now" (2 overs) → set openers/bowler → tap balls, try 🎙️ Voice and `1 4 0 wd 6` → check the 🔔 bell for "Live now" and wicket alerts → Undo.
5. AI Assistant → "Who is available for the next match?", "Ask everyone for availability for the next match", paste a score message → Confirm.
6. Signed out on `/live`: tap "AI Assistant" → "What's the live score?", "Scorecard for 19 Oct 2024", then try a score message and check it asks you to sign in.
7. Assistant page → Insights panel; chat: "How can Amit G improve?", "Suggest the best playing XI", "Season outlook".
8. Plans: open `/pricing` signed out and signed in (see "Subscriptions and plans" → "How to test").

## Retired out (RO) on paper scorecards

Request (Oct 2026): on our scorecards "RO" means Retired Out, not Run out (most batters retire).

- `app/ai_vision.py`: `ro_meaning()` reads `SCORECARD_RO_MEANS` from `.env` (`retired out` by default, or `run out`). The AI prompt tells the model what "RO" means and asks it to copy the HOW OUT text into `dismissal.written_as`.
- `_normalise` turns any batter whose HOW OUT is written "RO" / "R.O." / "R/O" into the club meaning, and `review_notes` adds "Ben: 'RO' on the card was read as retired out…" so the scorer can change one with Edit if needed.
- `app/main.py` `_scorecard_dismissal` shows a bare "RO" the same way on every scorecard page. Retired out counts as a wicket; retired hurt / retired not out does not.
- Scorecards read before this change keep what was saved: open the card → ✏️ Edit → set How out to "retired out" → Save (or press 🤖 Read with AI again).

## Screen size and zoom

Request (Oct 2026): "the screen should not zoom in and out".

- Every page (all `app/static/*.html` and the inline pages in `app/main.py`) uses `<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, viewport-fit=cover" />`.
- `app/static/styles.css` (end of file) sets `overflow-x: hidden` / `clip` on `html, body` so nothing makes the page wider than the screen, stops phones enlarging text on rotate (`text-size-adjust: 100%`) and uses `touch-action: manipulation` so double-tap does not zoom.
- Result: on phones and tablets the page is fixed to the screen width (no pinch or double-tap zoom, no sideways scroll).
- Laptop/desktop: `app/static/zoom_lock.js` (loaded in the `<head>` of every page, right after the viewport meta) blocks Ctrl/Cmd + "+" / "-", Ctrl + mouse wheel and trackpad pinch. Ctrl + 0 (back to 100%) still works. Chrome remembers an earlier zoom per site, so if the page is already zoomed out the script shows a note "Press Ctrl + 0"; the browser's own menu zoom cannot be blocked by a web page.
- When adding a new page, copy the same viewport meta, the `zoom_lock.js` script tag and link `/assets/styles.css`.
- How to test: restart the app, press Ctrl + F5, then in Chrome DevTools (F12 → phone icon) pick a phone and check you cannot pinch-zoom or scroll sideways on Home, Matches, Score and Scorecards.

## Subscriptions and plans

Model (soft launch, Oct 2026): keep the core cricket experience free; one paid plan, **Pro**, for managing a team, automation, AI and unlimited history. Free is the default for every new account.

| | Free ($0, default) | Pro ($9/month or $90/year) |
|---|---|---|
| Live scoring, guest matches, player/club stats, view scorecards | ✓ | ✓ |
| Scorecard photo uploads (captains / club admins) | 2 / month | Unlimited |
| AI Assistant tasks and AI Live Scorer | **1 free AI match** | ✓ |
| Upcoming matches with availability, rosters, Playing XI, multi-club | – (players of a Pro club can mark availability) | ✓ |
| Alerts and live score updates to players | – | ✓ |
| Analysis (predictions, tips, best XI, outlook), match intelligence, cross-club stats, priority support | – | ✓ |

- Yearly is **2 months free** ($90 instead of $108, i.e. $7.50 a month). **Monthly is pre-selected** on `/pricing`; `?billing=yearly` opens it on Yearly.
- The earlier **Super ($4.99/month)** and **Premium ($100/year)** plans were folded into Pro. Stored `super` / `premium` rows (including the 60-day launch trial) now read as Pro (`LEGACY_PLANS`, `normalize_plan` in `subscriptions.py`); nothing in the database needed changing.

### How plans work
- **Code:** `app/subscriptions.py` (plans, features, trial, free AI match, Stripe), `app/ai_scorer.py` (AI Live Scorer), helpers `_plan_for`, `_has_feature`, `_require_feature`, `_ai_allowed`, `_club_is_paid` in `app/main.py`. Each feature has a minimum plan in `subscriptions.FEATURES`; change prices, limits or features there.
- **Plans belong to a user.** Site admins (superadmin) always get Pro. A club counts as **paid** when one of its captains or club admins is on Pro; then every player in that club can mark availability and gets match and live score alerts without paying.
- **Trial:** users created before plans were switched on got **60 days of Pro** (`source = trial`); after it ends they drop to Free automatically. New users start on Free.
- **One free AI match:** a Free user may use the AI Assistant tasks and the AI Live Scorer on one match. The first match they use AI on becomes their free AI match (table `app_ai_trial`, `claim_ai_trial`); AI keeps working on that match, any other match answers 402 "Your free AI match has been used". `/api/subscription/me` returns `ai_trial {used, match_id}`; the user payload has `ai_trial_open`.
- **Default plan (Amit, Oct 15):** users without an explicit admin or Stripe plan get `CRICKETCLUBAPP_DEFAULT_PLAN` (`app/subscriptions.py` `configured_default_plan`; `premium` / `super` mean Pro). It defaults to **pro** while developing; set `CRICKETCLUBAPP_DEFAULT_PLAN=free` before launch. It also updates users whose plan still comes from the automatic default, never explicit admin or Stripe plans.
- **Upload quota:** counted from `archive.upload` rows in `app_audit_log` for the current calendar month (resets on the 1st).
- **Tables** (created automatically): `app_subscriptions`, `app_subscription_meta`, `app_payment_events` (Stripe webhook log), `app_ai_trial`.
- **What is locked** (HTTP 402 with an upgrade message; `static/plan_gate.js` shows an "Upgrade" pop-up on every signed-in page):
  - `POST /api/scorecards/upload` → monthly quota.
  - `POST /api/auth/select-club` and `/clubs/select` → switching away from your home club needs Pro (`multi_club`).
  - `POST /api/player/availability`, `/api/player/season-availability`, `/api/matches/{id}/availability` → `availability` (you or your club on Pro); changing someone else's → `match_roster`.
  - `POST /api/matches/{id}/lineup` → `playing_xi`.
  - `POST /api/muse/execute`, `POST /api/muse/confirm-score`, `POST /api/matches/{id}/ai-scorer` → Pro, or the free AI match.
  - `POST /api/chat` (Assistant page) → predictions, tips, best XI and outlook questions need Pro.
  - Live score alerts after each ball are only sent when the scorer or the club is on Pro.
  - `GET /api/insights/me` → Free gets form and club record; Pro adds the rest. Locked parts come back in `locked`.
- **Never locked:** live scoring (Quick Score buttons, basic voice and shorthand), guest matches, stats, rankings, scorecards, public pages and the public AI Assistant.

### Plans page (`/pricing`)
- Files: `static/pricing.html` (signed in), `static/pricing_public.html` (signed out), `static/pricing.js`, `static/pricing.css`.
- Shows the Free and Pro cards with a **Monthly / Yearly** switch (Monthly selected), a comparison table and FAQ. Signed in, "Your plan" shows the plan, trial days left or renewal date, uploads used this month and the free AI match.
- **Site admins** also see "Manage plans": counts per plan, a form to set any user's plan (Pro / Free, number of days, 0 = no end, note) and a list of every user's plan. Use this for cash payments, club deals or while Stripe is off.
- APIs: `GET /api/plans` (public, includes `default_plan` and `default_interval`), `GET /api/subscription/me`, `POST /api/subscription/checkout {plan: "pro", interval: "month"|"year"}`, `POST /api/subscription/portal`, `POST /api/stripe/webhook`, `GET /api/admin/subscriptions`, `POST /api/admin/subscriptions/set {user, plan, days, note}` (superadmin).

### Switching on Stripe payments
1. In the Stripe dashboard create one product "Pro" with two recurring prices: **$9 every month** and **$90 every year**. Copy their price ids (`price_…`).
2. Create a `.env` file next to the `app` folder and fill in `STRIPE_SECRET_KEY` (start with a `sk_test_…` key), `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY`, `STRIPE_WEBHOOK_SECRET` and `APP_BASE_URL` (the address people use to open the app). The old `STRIPE_PRICE_SUPER` / `STRIPE_PRICE_PREMIUM` are no longer used.
   - Keep `CRICKETCLUBAPP_DEFAULT_PLAN=pro` while developing; set `CRICKETCLUBAPP_DEFAULT_PLAN=free` in the production environment before going live.
3. Add a webhook endpoint in Stripe pointing to `https://<your site>/api/stripe/webhook` with the events `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted`. For local testing use the Stripe CLI: `stripe listen --forward-to localhost:8090/api/stripe/webhook`.
4. Turn on the Customer Portal in Stripe (for "Manage billing").
5. Restart the app. `/pricing` then shows "Choose Pro monthly / yearly" buttons that open Stripe Checkout. After payment the webhook switches the plan on; cancelling in the portal moves the user back to Free at the end of the period.
- No extra Python package is needed (Stripe is called with `urllib`). `.env` is in `.gitignore`: never commit real keys.

### AI Live Scorer (Pro, or the free AI match)
- In Quick Score tap **🤖 AI Scorer**. The microphone keeps listening (Chrome/Edge); you can also type. Say what happened: "four", "dot", "wide, then two runs", "no ball and a six", "two leg byes", "three dots", "bowled", "caught by Sam", "undo".
- `POST /api/matches/{id}/ai-scorer {text, innings_number}` → `ai_scorer.interpret()` splits the phrase into ball events, `ai_scorer.validate()` checks them against the innings and returns the projected score.
- The page then saves each event through the normal `POST /api/matches/{id}/scorebook/ball`, so the scoring engine still does all the cricket maths. Wickets open the usual wicket pop-up pre-filled.
- Free users see a "🎁 try AI on one match for free" note; after their free AI match the button shows a 🔒 and a link to Pro.

### How to test (plans)
1. Restart the app. Sign in as the site admin and open `/pricing`: you should see Pro ("Site admins always have every feature") and the "Manage plans" panel.
2. In "Manage plans" set a club admin (e.g. `clubadmin1`) to **Free**. Sign in as them: `/pricing` shows Free, "0 of 2 uploads used" and "You have 1 free AI match"; the third scorecard upload in a month is refused.
3. Use the AI Scorer or an AI Assistant task on one match (works), then on another match (Upgrade pop-up "Your free AI match is used").
4. Set the same user to **Pro** for 30 days: availability, Playing XI, predictions and AI work on every match; a Free player in that club can now mark availability.
5. Stripe (optional, test mode): fill `.env`, restart, run `stripe listen`, choose Pro monthly on `/pricing` and pay with card `4242 4242 4242 4242`; the plan changes to Pro.

## Change log

- 2026-10-15: Documented Windows local Ollama installation, chat/vision model setup, and health checks for AI Assistant and scorecard extraction.
- 2026-10-15: Improved local scorecard extraction with full-page and table-crop Ollama vision inputs, full innings/batting/bowling/extras JSON output, tagged-model discovery, portable HEIC conversion, and stale-JSON clearing on re-extract.
- 2026-10-15: Renamed the AI Muse interface and user-facing references to AI Assistant across signed-in, public, Home, Quick Score, and plan surfaces.
- 2026-10-15: Kept the uploaded original scorecard image visible beside the Admin Center snapshot and review JSON.
- 2026-10-15: Rendered the original upload directly in Admin Center review without displaying its URL.
- 2026-10-15: Arranged the Admin Center snapshot, JSON editor, and original image responsively, stacking the review panels on phones.
- 2026-10-15: Added the shared Scorecards snapshot and original-photo tabs beside each Admin Center archive review JSON.
- 2026-10-15: Reset scorecards and derived performance data across all years, including live fixtures; historical archives are retained for a fresh review starting with 2024.
- 2026-10-15: Reapplied the all-years score reset; archive images and records remain available for review.
- 2026-10-13: Automatic user plans default to configurable Premium for development; set `CRICKETCLUBAPP_DEFAULT_PLAN=free` at launch, which also switches accounts still on the automatic default.

- 2026-09-22: Navbar More menu, public Clubs page, header/menu/profile alignment, search and dark mode, Cricinfo-style phone layout.
- 2026-09-23: Digital scorecards by game date (#8).
- 2026-09-24: Signed-in navbar with account menu and floating Assistant; Sign In and public/signed-in Home redesigns (#9); Register redesign, strike-rate fix, shared look for inside pages (#5).
- 2026-09-24: Insights: form, predictions, tips, best XI, season outlook (#6).
- 2026-09-27: Public read-only AI Muse for signed-out visitors (`POST /api/public/muse`, `static/muse_public.js`).
- 2026-09-27: Matchday tile shows the last scored match when nothing is upcoming; Quick Score; AI Muse; in-app notifications and live score alerts; faster saves; AI tool instructions (this README rule, AGENTS.md, CLAUDE.md).
- 2026-09-29: Subscriptions and plans (#7): Free / Super / Premium, feature limits and upload quotas, 60-day Premium trial for existing members, `/pricing` page with admin plan management, Stripe Checkout + webhook (off until keys are set), Upgrade pop-up, plan-aware insights (match intelligence, cross-club stats) and the Premium AI Live Scorer in Quick Score.
- 2026-09-29: Merged the GitHub changes (README moved to `MD/README.md`, new `sports-system.css` look) with the plans work.
- 2026-10-04: Past matches locked (scores, availability, XI) and hidden from upcoming lists; AI Muse renamed back to "AI Assistant" on the button, answers through the LLM, and carries out tasks with Confirm/Cancel (`app/muse_agent.py`, `POST /api/muse/execute`); `READMELLM.md` is found in `MD/`.
- 2026-10-05: AI Assistant button on all public pages including Sign In/Register; public questions fall back to the LLM on public-only data; "next match" answers skip past games.
- 2026-10-11: Soft launch round 1 (call with Amit Sethi): plans are now Free (default) + **Pro $9/month or $90/year** (Monthly pre-selected; Super/Premium folded into Pro); **one free AI match** for Free users; captains and club admins can score and upload scorecards (`score_matches`, own club only); scorecard upload page with smart checks (same photo, resized photo, same match, Ollama check, mistakes), full digital scorecard preview with Publish / Something's wrong, site-admin review queue and duplicate clean-up (`/admin/scorecards`), alerts to site admins and players; simple menu Home · Matches · Score · Scorecards · Plans; app tour; sign-in `?next=`.
- 2026-10-11: OCR fix: a slow Tesseract pass (big phone photos take ~20 s) no longer throws away every OCR result (timeout 12 s → 60 s, each pass tried on its own). Tested with a real handwritten Heartlake scorecard: Tesseract alone can't read handwriting, so the upload is correctly sent to admin review; for real extraction install an Ollama vision model (`ollama pull qwen2.5vl:7b`).
- 2026-10-11: Typing in a scorecard by hand (Admin Center → Archives → "Import pasted extraction", JSON template like `heartlake_scorecard.json`) now runs the same upload checks and replaces old OCR flags; a batter whose card spelling differs from the roster ("Vinay" / "Vinny") is no longer counted twice; "retired out" counts as a wicket (plain "retired" stays not out).
- 2026-10-11: Handwritten scorecards: when the photo reading gives junk (Tesseract on handwriting), it is no longer shown as a scorecard (`ocr_rows_look_real` in `cricket_store.py`, status "Unreadable"); the preview page opens a **"Type in the scorecard"** form instead (teams, date, venue, overs, result, each innings' total/wickets/overs/extras, batters with how out/bowler/R/B/4s/6s, bowlers with O/M/R/W, live "batters + extras = total" check) saved through `POST /api/scorecards/{id}/manual` (uploader, own club's scorers, site admins), then the usual checks run. "Edit scorecard" corrects any upload the same way. Phone fix: long team names no longer make the scorecard wider than the screen.
- 2026-10-11: Handwritten scorecards read automatically by Claude's vision model when `ANTHROPIC_API_KEY` is set (`app/ai_vision.py`, upload flow + "🤖 Read with AI" button); AI-read and typed-in scorecards wait for Publish instead of being auto-approved; published-scorecard links fixed (`/scorecards/a-<id>`); the preview page also opens from a public scorecard address.
- 2026-10-11: AI scorecard reading can use Google Gemini's free tier (`GEMINI_API_KEY`), so reading handwritten scorecards costs nothing; Claude stays optional.
- 2026-10-12: The 🔔 bell opens a notifications list right under it (click again or Esc to close; tap an item to open it and mark it read; "Mark all read"; "Open all in the Assistant"); alert rows no longer get squashed.
- 2026-10-12: A batter with nothing written next to their name is shown under "Did not bat" (not as 0 with "imported from chatgpt/manual extraction").
- 2026-10-12: AI reading cross-checks each batter's runs column against their own ball-by-ball runs and copies the extras exactly as written; any mismatch or hard-to-read number is listed for the scorer ("Check Ben: the runs column reads 30, but the ball-by-ball adds up to 38"), stored in `ai_flags`.
- 2026-10-12: The upload page says which reader is used ("Photos are read by: Google Gemini (free AI)"), `GET /api/scorecards/reader`.
- 2026-10-12: AI reading no longer stretches extras to make the total fit (it re-reads the batters instead), flags "extras boxes add up to 52 but extras says 61", and writes the club's own name (not "HEART LAKE" vs "Heartlake Cricket Club" as two teams).
- 2026-10-12: Site admins can delete an upload (and its photo) from its scorecard page with "🗑 Delete this upload", e.g. to upload the same photo again; the site admin may delete any club's upload.
- 2026-10-12: AI reading double-checks itself: when batters + extras don't make the total, the model is shown the mismatch and reads the photo again (`sum_problems`, second pass); clearer check messages (match date / other team / second innings missing, with what to do).
- 2026-10-12: Public pages (Scorecards, Fixtures, Live…) show "My dashboard" and "Sign out" when you are signed in, instead of "Sign In" / "Register" (it looked like the app had signed you out); site admins get a "Scorecard checks" button on /scorecards.
- 2026-10-12: Gemini reading retries when Google says it is busy (503) and moves on to the next free Flash model; clear messages for busy / daily limit.
- 2026-10-12: Free offline scorecard reading with an Ollama vision model (`qwen3-vl:8b` / `:4b`) through the same AI reader (`_read_with_ollama` in `app/ai_vision.py`); used automatically when no Gemini/Claude key is set.
- 2026-10-14: Screen size lock: pages no longer pinch/double-tap zoom on phones (`maximum-scale=1.0` in every viewport meta, `touch-action: manipulation`) and never scroll sideways (`overflow-x: clip` on html/body); styles.css bumped to `?v=20261014a`. See "Screen size and zoom".
- 2026-10-14: Laptop zoom lock (`app/static/zoom_lock.js` on every page): Ctrl +/−, Ctrl + wheel and trackpad pinch no longer zoom; Ctrl + 0 still resets; note shown when the browser is already zoomed out.
- 2026-10-14: "RO" in HOW OUT is read as Retired Out (club rule, `SCORECARD_RO_MEANS` in `.env`, default retired out) by the AI reader and on scorecard pages; review note for every RO batter.
- 2026-10-16: Simple sign-in page (one card, no League leaders, player name only when needed). App tour now shows once per account after the first sign-in, with "what to do" steps that depend on the role (`app_tour_seen`, `/api/tour`). See "Simple sign-in page" and "Simple menu and app tour".
- 2026-10-16: First page: `/` opens Home when signed in (Live when signed out); sign-in goes to Home when the account has a club (Clubs only when it has none); tour skips "Pick your club" when not needed. See "First page".
- 2026-10-16: Shorter public menu: LIVE · Fixtures · Scorecards · Rankings · Sign In + More (Score, Clubs, Plans, Register). See "Public menu".
- 2026-10-16: Public bar: CricketCanClubs name by the logo, "Live scores" tab, More on the right without Dark mode, separate Sign out button; simpler /live page. See "Public menu" and "Simple Live page".
- 2026-10-16: Plan restrictions: no AI before sign-in (public assistant and guest AI Scorer); AI reading of scorecard photos is Pro, or the Free plan's one free AI try. See "Plans: what each group can use".
- 2026-10-16: AI Assistant answers greetings, cricket and app questions with Gemini (`app/ai_chat.py`), uses club data for club questions; no sign-in prompts when signed in on public pages; full-height right-side panel. See "AI Assistant answers (Gemini)".
- 2026-10-16: AI Assistant shows thinking dots, then types its reply; "Take the app tour" removed from the account menu (tour is only shown once to first-time users).
- 2026-10-29: Availability requests and match reminders under the bell: asked when a match is added (or 7 days before), a personal reminder 2 days before if not replied, "Tomorrow" the evening before, "Match today" on the day, and "Match changed" when the date / time / ground changes. See "Availability requests and match reminders".
- 2026-10-29: Start a new match against the same team makes a new match once the earlier one has started; the match list shows time and Score now / LIVE · Continue / Finished. Plans page shown during the launch ("Pro free during the launch", no payments). See "A new match against the same team".
- 2026-10-29: Captain / VC / keeper is now one line per team under the tick list (tap a box, pick a name); the buttons on every player are gone.
- 2026-10-29: Simpler captain / VC / keeper choice: tap C, VC or WK on the player's card in the line-up (the menus are gone).
- 2026-10-29: Captain, vice-captain and wicket keeper for both teams on the line-up screen (also read from (c) / (vc) / (wk) in a pasted list), shown as C / VC / WK tags; keeper first for a stumping. See "Captain, vice-captain and keeper".
- 2026-10-29: Balls are never lost: unsaved balls wait and retry by themselves (also after a reload), with a "No connection" banner; each ball has its own id so a retry is never saved twice. See "Balls are never lost".
- 2026-10-29: A new over can't start without a new bowler (closing the pop-up let the same bowler continue); the recent-balls row shows whole overs only. See "GT test match check".
- 2026-10-29: 🏆 HURRAY! celebration when a match is won (Score page and public page); no new balls once an innings is over (fixes "28/11"). See "HURRAY! when a match is won".
- 2026-10-29: Last 12 balls in one row (newest on the right, line between overs) on the Score page and the public scoreboard; "More" on the Score page lists every over and lets you fix any ball. See "Last 12 balls in one row".
- 2026-10-29: Full test before the Azure deploy (Azure-like server, 2 workers, GMT clock): ball saves 4 s -> 0.6 s, 27-byte replies instead of 1.6 MB, results only when the match ends and the chase ends at the target, undo re-opens a finished innings, innings-break and match-complete screens, "This over" fix, no bowler pop-up after the winning ball, safe database export / import, stale index repaired at start-up. See "Full test and fixes".
- 2026-10-29: App runs on Ontario time (`APP_TIMEZONE`, default America/Toronto) instead of the Azure server's GMT: match start times and "today" are now local. See "Local time".
- 2026-10-29: Public live scorecard rebuilt: full scoreboard (score, overs, rates, target / need, batters, bowler, this over), one row per batter and per bowler, extras, total, yet to bat, fall of wickets, ball-by-ball commentary with correct ball numbers. See "Public scorecard (Oct 29 2026)".
- 2026-10-29: Fixed "Match not found." right after starting a match on Azure: the in-memory copy of the data is now checked against a save counter (`app_store_version`) instead of the database file's time and size, which WAL mode often leaves unchanged; line-ups refuse a 12th player. See "Fresh data on every request".
- 2026-10-29: Easier live scoring on /score: tap player names instead of typing, one-tap pop-ups for next bowler / byes / no balls, wicket in 2-3 taps, tap any ball to fix it, Select all / Player 1-11 / WhatsApp paste for line-ups, and FOUR / SIX / WICKET / FIFTY / HUNDRED celebrations with a phone buzz on /score and the public live page (which now refreshes every 15 s). See "Easier live scoring".
- 2026-10-28: Saving writes only what changed: `save_store` compares each table with the database and writes only new, changed or removed rows (a one-score edit: about 3 row writes instead of about 3,600); same final data as before; `CRICKETCLUBAPP_FULL_REWRITE=1` turns it off. Groundwork for a cloud database. See "Saving only what changed".
- 2026-10-28: Phone menu: Sign out is only in the ⚙️ Settings sheet (not in the ☰ Menu); inside the phone app the website's own bottom tab bar is not drawn (the app's native tabs replace it), so there is one bar, not two (`site_tools.js`, loaded as `?v=20261028a`). Requested by Dhruvika after trying the Expo app on her phone.
- 2026-10-28: Phone apps moved to one Expo / React Native app in `mobile/` for iPhone and Android (cloud builds, no Mac needed); same tabs, camera upload, offline screen and icon. See "Phone apps (Expo)".
- 2026-10-27: App tour works inside the phone apps ("tap Score at the bottom") and first-time visitors get a 3-step welcome on Live; new Privacy policy page (/privacy) and "Delete my account" on the Profile page for the app stores. See "App tour in the phone apps and for visitors".
- 2026-10-27: Amit's Azure check: Home shows only your own club's scorecards and matches; one signed-in menu on every page (public pages too); Next match never shows a past game ("No upcoming match scheduled"); Plans stay hidden for the launch. See "Amit's Azure check".
- 2026-10-26: Phone apps for the Diwali launch: Android and iPhone apps with native tabs, camera upload, pull to refresh, offline screen, icon and splash; the website hides its own bottom bar inside the apps. See "Phone apps" and `MD/PHONE_APPS.md`.
- 2026-10-27: Edit fixes now show: a card typed in or fixed with Edit (`POST /api/scorecards/{id}/manual`) is saved as the reviewed copy and always wins over the AI reading (`_scorecard_pick_template`); before, the AI copy won when it listed more names, so fixes seemed lost. Re-read all never re-reads published cards or cards fixed by a person. Gemini errors now say what Google answered, and a 500 is retried without the worked examples.
- 2026-10-27: Trained the AI reader with worked examples: 2 checked real scorecards (`app/ai_examples/`, in git) are sent with every read, plus rules for rows, shirt numbers, bowling boxes and extras tallies, a totals check that only fixes a number when exactly one reading adds up, and `scripts/add_ai_example.py` to add more. See "Worked examples".
- 2026-10-26: Re-read never makes a card worse: Gemini reads the same photo a little differently each time (Oct 26: 3 cards that added up came back a few runs off), so if a new reading has more problems (runs / wickets / other team) than the earlier AI reading, the earlier one is kept and the report says so.
- 2026-10-25: Launch: everyone on Pro (Amit: "We will not start any subscription at launch so everyone should be at premium subscription... Once we mature then we will start subscription"). `CRICKETCLUBAPP_SUBSCRIPTIONS` (default off): while off, every account gets all Pro features (plan source "launch", no trial end), /pricing redirects to Home and every link to /pricing (Plans menu item, account menu, Upgrade buttons) is hidden via `/api/public/config` (multipage.js / public_header.js). Set `CRICKETCLUBAPP_SUBSCRIPTIONS=on` in .env when payments start. New `DELETE /api/admin/users/{id}` (site admin) deletes a sign-in account and its sessions/plan/notifications, for removing test accounts; it never deletes yourself or a site admin.
- 2026-10-24: Checked the 19 cards that didn't add up against their photos and trained the reader on what went wrong (reader version 2026-10-24): tick marks after the ball-by-ball ("7", "77", ">>") are not runs (IMG_1894 read "477" as 18); the RUNS / TOTAL RUNS column wins over the ball-by-ball; a total equal to the batters' runs gets the extras added (IMG_5007: 155 + 19 = 174); the year is only "fixed" for look-alike last digits (0/6, 1/7, 3/8, 4/9), so a real 2024 card stays 2024; photos added from img/ don't use their import date as the photo date. Re-read option "Only cards with problems" (Admin Center) / `--only-problems` re-reads just the cards whose runs or wickets don't add up or whose other team is missing, to save the free daily limit. Gemma 4 (`gemma4:e4b`) added as an Ollama backup model.
- 2026-10-23: Re-read took about 8 minutes per card because the first Gemini model kept timing out (3 tries x 2 minutes) before the next model answered. Now a timeout moves straight to the next model, busy is retried once, and a model that timed out / was busy / hit its limit is skipped for 20 / 10 / 60 minutes (`_GEMINI_SKIP` in `app/ai_vision.py`), so later cards go straight to a model that answers.
- 2026-10-22: Ollama backup when Gemini's limit runs out (`ai_vision._read_once`): if Gemini answers "limit"/"busy" and Ollama with a vision model (e.g. `ollama pull qwen3-vl:8b`) is running on the computer, the photo is read by Ollama instead (free, unlimited, slower, less accurate). Those cards get the note "Read by the local AI (Ollama)... check every number", skip the second look, and are not stamped with the reader version, so the next "Re-read all" with the skip box reads them again with Gemini. Uploads and the Admin Center re-read both use it; without Ollama the re-read still stops and continues the next day.
- 2026-10-22: Each AI read is stamped with the reader version (`ai_vision.READER_VERSION`, saved in `ocr_pipeline`). "Skip cards already read by the newest AI reader" (Admin Center) / `--skip-done` skips only those, so a re-read stopped by the free daily limit carries on the next day.
- 2026-10-22: Reader trained on the re-read results: (1) photos are never read with the "lite" Gemini model (it got extras/totals wrong); when the better models hit the free limit, reading stops and continues later; (2) big phone photos are also sent as zoomed top and bottom halves (up to 3072 px) so small handwriting is sharper; (3) our players' names are only matched on our side of the card (the other team's DILLON stays DILLON); (4) an empty TOTAL column uses the batter's ball-by-ball runs, with a note.
- 2026-10-22: First real re-read (17 of 36 cards) showed two problems, fixed: the name matcher changed shared first names ("AMIT" -> "Amit S" when there are Amit S and Amit G) and different names ("Simran" -> "Imran"); it now only fixes a clear misread of one player (MESHAD -> Heshad, DILLON -> Dhillon, Kiron -> Kirron). Cards with no date written no longer get the date the photo file was copied (2026-10-16); `refresh_archive_dates` ignores `filesystem-modified` photo dates.
- 2026-10-20: Clean up and re-read all scorecards (Admin Center button + `scripts/scorecards_reread_all.py`), sample-card accuracy test, learned names kept in `app/ai_learning.json` (committed to git).
- 2026-10-20: Faster photo reading: one AI read on most cards, low thinking time, seconds counter on the upload page.
- 2026-10-20: Saving no longer fails when an older upload's photo file is missing (`_copy_for_review` in `cricket_store.py` skips the duplicate review copy). Delete a scorecard upload from its page (🗑 Delete this upload) or Admin Center, then upload the photo again.
- 2026-10-20: Stats for every player, invite / add-performance only for admins, no ages in the roster, Pro "Season by season" table, "See 2025" hint (`stats_page.js`). AI Assistant gets a club snapshot (players, matches, results, scorecards, top scorers, your own numbers) and better instructions.
- 2026-10-20: Amit's feedback: Player name field always shown on /signin again (for sign-in without a password); after sign-in everyone goes to /clubs to pick their club; Clubs and Stats (/dashboard/widgets/performance) are back in the top menu (`shared_header.html`, `multipage.js`).
- 2026-10-19: AI reader reads without manual edits: name letter-by-letter rule, bowling figures from the analysis boxes, bowlers' wickets from the batting card, photo date from the WhatsApp/IMG file name, season follows the date read.
- 2026-10-19: AI reader learns: RUNS(BALLS) rule, ball-by-ball count check, photo date for the year, known names, and name fixes saved per club (`app_ai_corrections`) and used on the next read. See "How the AI reader learns".
- 2026-10-19: Fixed "Upload failed." on /scorecards/upload when AI reading is on (the plan check used an undefined `current_club_id`; now `upload_club_id`).
- 2026-10-18: Merged Amit's Oct 16 commit (local Ollama vision reader with focused crops in `cricket_store.py`, "AI Muse" renamed "AI Assistant" across the app, tests). Upload/Re-extract order kept: Gemini AI reader first, then Amit's local reader; the local reader now also fills `review_template_json`.
- 2026-10-17: Admin Center Re-extract shows progress and the result on the scorecard card and no longer runs twice; Scorecard checks also lists "Ready for review" uploads.
- 2026-10-16: Merged Amit's Oct 15 Admin Center review (snapshot + JSON + original image, HEIC previews, configurable default plan, now `pro` / `free`) with the soft-launch work; Re-extract now uses the AI reader; AI result kept as the reviewed copy; 2-innings card fix. See "Re-extract uses the AI reader".
- 2026-10-16: AI duplicate check now uses the configured AI (Gemini first) instead of only Ollama, on upload and with "🤖 Ask AI to find more duplicates" on /admin/scorecards.
- 2026-10-06: Plan-based menu (Free: scoring + viewing; paid: everything) with page guards; line-ups (2–11 per side) required before scoring; guest matches without sign-in (match code); Home overview with Live now / Recent results / Coming up; phone overflow fix on Clubs and Admin.
- 2026-10-30: Live page looks like a cricket score app: team rows with badges, "need X runs in Y balls", Live / Scorecard / Commentary tabs, batters and bowlers tables, partnership, over-by-over balls; refreshes every 10 s; server replies are gzipped (88 KB -> 8 KB). See "Live page like a cricket score app".
- 2026-10-30: Whole app uses the Roboto font, like Cricbuzz. See "Live page like a cricket score app".
- 2026-10-30: Fixed: both teams always get the same overs (a 1-over match gave the chasing team 2 overs).
- 2026-10-30: Live tab now looks like Cricbuzz, with the ball strip by over and Win Probability. See "Live page like a cricket score app".
- 2026-10-30: Scorecards show "c & b Bowler" instead of "c Bowler b Bowler".
- 2026-10-30: AI scorecard reader trained more: worked example 3 (printed card), caught-and-bowled rule, and cross-checks of bowling runs / overs / wickets / boundaries that make it look again. See "How the AI reader learns".
- 2026-10-30: Scorecard page restyled like the live page (Cricbuzz look). See "Live page like a cricket score app".
- 2026-10-30: Uploaded scorecards look exactly like scored matches (same header, tabs, innings bars and tables).

## New UI Look and Feel

## 1. Typography & Global Layout Foundation
Prompt for Copilot Chat / Panel:

> Write a clean, modular CSS layout configuration for a premium light-themed sports website canvas. Import "Anton", "Inter", and "Space Mono" from Google Fonts. Set the global background canvas color to an off-white `#F8F9FA` and default text to `#1A1A1A`. Create two primary structural heading classes:
> 
> 
> 1. `.sports-title`: Uses the font 'Anton', uppercase, large font sizing, for aggressive sports hero typography.
> 2. `.sports-subtitle`: Uses 'Inter', weight 800, uppercase, letter-spaced, colored in crimson red `#D32F2F`.
> Also, include a `.stat-card` class that mimics a floating dashboard panel: background white, smooth rounded corners, a subtle 1px border (`#EAEAEA`), and an ultra-soft drop shadow.

---

## 2. High-Performance Sports Table Grid
Prompt for Copilot Chat / Panel:

> Design a clean HTML/CSS data table layout engineered for a sports statistics leaderboard. Structure a table layout named `.custom-table` that removes harsh internal grid borders. Give table headers (`th`) a muted gray color (`#6C757D`), uppercase transformations, and generous layout padding. Table cells (`td`) must feature comfortable spacing, a thin baseline row divider, and use the 'Inter' font. Create two helper styling badge classes:
> 
> 
> 1. `.rank-badge`: A compact inline-block background badge colored in crimson red `#D32F2F` with white text rendering numerical metrics using 'Space Mono'.
> 2. `.numeric-data`: Applies the 'Space Mono' font family explicitly to numerical metrics like runs, averages, and wicket metrics to optimize visual scanning.

---

## 3. Integrated Charting Configuration (Plotly/Matplotlib)
Prompt for Copilot Chat / Panel:

> Generate a programmatic bar chart configuration function using Plotly Graph Objects that seamlessly binds into a light-themed user interface canvas. The chart needs to process individual player label arrays on the X-axis against their total scoring numbers on the Y-axis. Style the chart elements according to these visual constraints:
> 
> 
> - Set bar fill colors strictly to athletic crimson red `#D32F2F` with a slightly deeper `#9A1B1B` outline border.
> - Strip out all solid background panels (`plot_bgcolor` and `paper_bgcolor` must be completely transparent).
> - Enable subtle horizontal grid lines using a very soft gray `#EAEAEA` for the Y-axis only.
> - Bind the chart font configuration directly to the 'Inter' typeface family.
