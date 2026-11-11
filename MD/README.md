# CricketClubApp

Local-first CricketClubApp product with a web app plus matching iOS and Android app surfaces. The three surfaces are kept in lockstep so the same cricket workflows are available everywhere.

## Instructions for AI tools (read first)

Any AI assistant or coding tool working on this repository (Claude, ChatGPT, Copilot, Cursor, Gemini, etc.) must follow these rules:

1. **Document every change in this README.md.** When you add or change a feature, page, API, data rule or workflow, add or update the matching section below (and add a dated line to "Change log") in the same change. Future developers and AI tools rely on this file as the single source of truth.
2. **Record the user's request.** Add the requirement, in plain words, to "Prompt And Requirement Log" so the reason behind the behaviour is kept.
3. **Keep the three surfaces in lockstep.** The iOS and Android apps load these web pages, so web changes must work at phone width (390px) as well as laptop width.
4. **Never commit local data or secrets.** Files in `app/data/` (`*.db*`, `*_cache.json`, `.stats_version`), `app/uploads/` and the `.env` file (Stripe keys) stay out of git.
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
- The signed-in Clubs page shows only the current club to superadmins and keeps the full registered-club list in Admin Center. Other signed-in users see only clubs linked to their identity; never show every club by default after login.
- The dashboard player snapshot must default to the authenticated member linked to the account. It must not fall back to another roster member just because that member appears earlier in the list.
- If a player belongs to multiple clubs, the player profile may show cross-club career history, but each club dashboard remains club-local.
- Sign out must invalidate the server session and clear the browser auth state.
- Success and loading chatter should stay quiet in the UI unless it is needed for a real error or actionable confirmation.

## Azure data architecture

- Production infrastructure is provisioned in **Canada Central**: Azure SQL logical server `cricketcanclubs-prod-sql` and the single free-limit database `cricketcanclubs-prod` (General Purpose Serverless, Gen5, 2-vCore maximum, 60-minute auto-pause, auto-pause when the free limit is exhausted). The database is currently empty and has no application firewall rules.
- Test remains on SQLite. Do not create a second Azure SQL database for test because the subscription's free monthly allowance applies to only one database.
- The Canada Central Key Vault is `cricketcanclubs-prod-kv`. The `GEMINI-API-KEY` secret and generated SQL administrator password are stored there. The production App Service uses its system-assigned managed identity with the **Key Vault Secrets User** role and a versionless `GEMINI_API_KEY` Key Vault reference; never copy the secret into source code, deployment packages, or logs. The previous East US vault `testkeyvault179` was soft-deleted on 2026-10-28 and is recoverable through its 90-day retention period; it was not permanently purged.
- The application still opens SQLite directly and uses SQLite-specific schema and PRAGMA operations. The provisioned SQL database is not yet connected and contains no migrated production data. Keep production on its existing SQLite database until a SQL Server-compatible data layer, a backed-up data migration, and production read/write validation are complete. Test must continue using SQLite.
- The 2026-10-28 production redeploy verified `/api/health`, a Gemini scorecard reader, and a successful synthetic scorecard extraction using the Key Vault secret. Production data remains on the existing persistent SQLite file at `/home/site/cricketcanclubs/cricketclubapp.db`; the Azure SQL database is paused and empty. Do not cut over the database until the SQL-compatible data layer, a backed-up migration, and production read/write validation are complete.
- **SQLite journal mode on Azure:** the live file is `/home/site/cricketclubapp/cricketclubapp.db` (`CRICKETCLUBAPP_DATABASE_FILE`). It sits on Azure Files (SMB), where WAL is unsafe. When `WEBSITE_SITE_NAME` is set (Azure), `_auth_connection` in `app/main.py` and `_connection` in `app/cricket_store.py` use `journal_mode = DELETE`; local runs keep WAL.
- **2026-11-04 production DB recovery:** signin returned 500 with `sqlite3.DatabaseError: file is not a database` because page 1 (header and schema root) of the live DB was overwritten. The 8 surviving `sqlite_master` leaf pages were used to rebuild page 1, the result was `VACUUM`ed and uploaded after the app was stopped, and the corrupt original was kept on Azure as `cricketclubapp.db.corrupt-20261104`. Integrity check passed. To check a production DB, download it via Kudu (`/api/vfs/site/cricketclubapp/`) and run `PRAGMA integrity_check`.

## Prompt And Requirement Log

This section captures the user requirements in the order they were given and refined during the build.

### November 2026 profile stats as cards
- "this is not looking good as this is not professionally done... come up with better design and keep all batting bowling under same year or under club not spllitted by season or year or club and multiple times" (the profile shows three career tiles, then one card per season and one per club. Each card has Batting, Bowling and Fielding as separate labelled groups; the groups sit side by side on laptop and stack on phone.)
- "add some space and move to left a you have alot of white space and try to use tiles in between..look and feel is not good" (profile: left aligned, group tiles with gaps, more space between sections.)
- "should the Clubs page player snapshot also get bowling and fielding columns? Yes" (the Clubs page player snapshot, Year wise and Club wise tables, gets Ov, Wkts and Econ columns after St, with a Batting / Fielding / Bowling band row.)

### November 2026 batting, bowling and fielding kept separate
- "is not making sense to include bowling under batting stats and batting under bowling stats or field.. please keep it simple and show only batting under batting, bowling under bowling and fielding under fielding stats" (each stats card and table shows only its own category.)

### November 2026 player profile shows bowling and fielding stats
- "no in the players/<player id> should add bowling and field stats here" (the player profile shows bowling and fielding alongside batting: bowling tables for career, season and club, and catches in the batting tables.)

### November 2026 profile recent matches and summary
- "do the same for recent matches as well on the same page and on the summary above as well..this page is the most visted page has to stand out from others" (Recent matches uses the same Batting | Bowling | Fielding bands per match, with catches and run outs from each scorecard. The summary tiles get one accent colour per group and larger figures.)

### November 2026 ranking cards show all stats and link snapshot names
- "not its not there on the Ranking page, on the focussed club snapshot. Also, if you are showing the bowling stats of a player or a fielding snapshot then should show the player's bowling stats and fielding stats alongwith the batting stats...same as batting stats" (the Focused club snapshot Top Batter name links to the profile; every batting, bowling and fielding ranking card, and the Home preview, shows batting, bowling and fielding totals for the player.)

### November 2026 Home page cached between visits
- "we should cache the home page if it has loaded the first time...while going back and forth it relaods and time consuming activities." (the Home dashboard and the Home overview feeds are kept in the tab's sessionStorage: a return visit draws the last copy at once, then refreshes it in the background and redraws only when the data changed. The cache is cleared on sign-in and sign-out.)

### November 2026 player name links on Home
- "On the Home page and anywhere we show the players name ensure we have the hyperlink to it to show the player profile which is players/<player_id>" (every player name shown on the Home page links to `/players/<player_id>`.)

### November 2026 name claim approval scope
- "both club admin and superadmin. Club admin sees its own club players and superadmin for all" (confirms the name claim and name matches rule: superadmin sees and decides everything; a club admin or captain sees and decides only for players in their own clubs, via `_reviewer_can_decide`. A name-matches group is shown only when the reviewer can see every member in it.)

### November 2026 name matching for initials
- "Its working but tell Bim and Bim B is not visible, Amit and Amit S etc not shown...also once you merge then put the other name into that player's alias so that next time it is not be a problem" (a name plus a 1-2 letter initial, e.g. "Bim" / "Bim B", counts as a match in Name matches and merge requests; a merge already adds the removed name to the survivor's aliases.)

### November 2026 player merge requests
- "allow them to merge" followed by "yes build it" (player can ask to merge a similar-name record; a club admin or superadmin approves it in Name matches.)
- "show on the club page if there is any match and over 60% match else don't show" (the merge card moved from the profile page to the club page. Later changed to 50%, see below.)
- "i can see it on player home page but there should be another button to reject it and once rejected it should save that response and does not show. Show the details of that match like player full name, club its associated with and matches that it has played in some professional design look and feel" (adds a "Not me" button that is saved, and a "View details" panel on each suggestion.)
- "You should give both option to merge into older name or new name and reject as well and then save the response... match percent should be 50%" (the card offers "Merge into older record" and "Merge into newer record" plus "Not me"; the threshold is now 50%.)

- "once this is learnt and merged then this engine should run during new match scorecard uploads and should identify this and let the uploader know instantly after the scorecard is uploaded that this is a match and merged into the other name..." (flag only, no auto-merge: the upload message and the scorecard preview show the match, and the uploader can merge into the older or newer record or ignore it.)
- "keep the match percentage to 75% threshold as it is halucinating", then "threshold should be 80%" and "everywhere 80% it has to be consistent", then "keep 75% then" (the upload name check and the club-page card both use one constant, `PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.75.)

### November 2026 AIDuplicateEngine (clubs and aliases)
- "it should not be just name matches, check his clubs, aliases, primary club and secondary club and then try to create a robust AI engine to identify the most near player and recommend for merging.. not just every name ..." (the match score now uses name, aliases, primary and secondary clubs, and explains each reason. The top candidate is marked "Recommended". Two different people who bat in the same match are never suggested. Still a deterministic rule-based engine, not an LLM, and it never merges by itself.)
- "call this engine as AIDuplicateEngine and use it where ever applicable" (the engine is named `AIDuplicateEngine` in `app/ai_duplicate_engine.py` and is used on the club card, merge requests, the upload name check and Admin Center Name matches.)
- "at or above..any uploader should be shown" (the 75% threshold now includes exactly 75% (`>=`), and any uploader sees the upload name check match. Only reviewers get the merge buttons.)
- "how about merge into other or newer name you should have both options and rejection" (Admin Center Name matches now shows three actions per pair: "Merge into <older> (older)", "Merge into <newer> (newer)" and "Not the same player". The keep choice is sent as `keep_member_id`. "Not the same player" is saved in `app_name_match_rejections` and hides the pair for all reviewers.)

### November 2026 member merge
- "I can see this now, but there is no way to merge them..allow them to merge". Decisions: superadmin, or a club admin who administers both players' clubs, can merge; the older record survives; merges must be reversible (superadmin undo).

### November 2026 name matches page
- "player duplication management is not visible..I couldn't find anything related to it in the application..provide me the page to show name matches" (answered with a read-only "Name matches" card in Admin Center, Archives section; no merges or writes.)

### November 2026 duplicate player Phase 0
- "Revise the Phase 0 implementation scope. IMPORTANT: Keep the existing sign-in functionality completely unchanged for now." Replace automatic same-name member merging with a claim request and approval workflow; do not delete or merge members based on name similarity; preserve Player IDs and historical references. Consolidate name normalization into one shared implementation used by `main.py` and `cricket_store.py`. Do not build the duplicate detection engine.

### November 2026 Azure internal server error
- "hyperlink on player names are missing to show the stats in the recent results" (the live page's scorecard links names to `/players/<id>` even when the match has no lineup, using the linked published card's player ids.)
- "Uploaded match and live match format of the scorecard is not consistent. It should be consistent in all the pages from where the scorecard is seen not just home page or archives or scorecards or live matches and missing links on players names to see their stats...please be consistent whether uploaded scorecard or live should be same like live scoring" (one innings markup in `scorecard_view.js` for the uploaded page, Admin preview and live fallback; player names link to profiles on the live page via `match.player_keys`.)- "are same http://localhost:8090/scorecards/a-fa879005 but why shown different and different format and have different match id" (the live page now uses the linked scorecard's Match ID, M-FA879005, and the same score text.)
- "issue persists, score card format in live score and Recents scores is not matching..live results missing score cards for each innings but score is shown in different format" (all out now shows "154/10" everywhere, and innings with data open by default so each innings' card is visible on the live and published pages.)
- "can youuuuuuu compare the stylesheet on the scorecard..how is this same as other scorecard...what is this nonsesne" (the live page's fallback innings were plain boxes with "215/9" and no toggle; the published page had a clickable ▾ header, "215-9" and different CSS. Both now use the same markup and the "runs/wickets" format.)
- "why the score formats are different in recent and latest..can we be consistent" (Home Recent results showed "215" while Latest scorecards showed "215/9"; both now use runs/wickets).
- "still this is not fixed and I don't see any data in the scorecard though it is there in the other place..." (the live page for 2026-08-23-carl still showed "Upcoming" and an empty scorecard; the live page now shows the published scorecard).
- "/scorecards/a-fa879005 has the complete scorecard but why is missing on live/2026-08-23-carl when both are same" (the live match page was empty while the published scorecard had the innings; fixtures should take the scores of their matching scorecard).
- "Why these scorecards scores are not coming when the same is coming in the Latest Scorecards" (home Recent results showed "Result not recorded" while Latest scorecards had the scores).
- "There should be a way to delete the duplicates if the innings match" (scorecard preview flags: "Only one innings is on this photo", "Possible duplicate of IMG_3286.png / IMG_3286.HEIC / IMG_3284.jpg").
- "3 lines ... should be more professionally done" (home page greeting header).
- "please put only 1 greeting" (home page).
- "Good evening / Season 2026 / Good morning, Amit" - the two greetings on the home page disagree; both should follow local time.
- "Amit CC still shows 0 members; instead of 'Welcome back, Amit' say good morning/afternoon/evening by local time; error on the Amit CC home page: can't access property venue, match.details is undefined".
- "match count don't tally in this page... 8:9 how is it possible" (player stats: Year wise 8 matches vs Club wise 9).
- "Under Stats page for Amit CC, Team roster and Team played scoreboard is showing all 0 data whereas they have data in 2024 which is shown in season by season".
- "good morning amit is in two lines..font also should be smaller than Season" (home hero).
- "You did not fix the issues with Amit CC club, no members shows in it, an error message pops up and in Prod I can't find Amit CC in my login so data seems corrupted in Prod than in Local..need a fix too".
- "Just uploaded the scorecards of a match between Heartlake CC and Amit CC... Amit CC shows 0 players under it though the match was published and had players in it which should be visible in the clubs home page etc".
- "remove texts like public mode read only, Reading scorecard from Google Gemini.. Use appropriate and professional text like reading scorecard".
- "We need a back plan for db, once we go live we cannot afford to lose the data".
- "Amit CC still not auto-registering as a club from the played game. Every match should auto register" (card "Amit 11 vs Heartlake Cricket Club", 16 Jun 2024; also "'Ravi' was changed to 'Rams' (corrected on an earlier card)" while Ravi and Rams both bowled).
- "When I upload the score for both the teams through one team upload, it creates two match ids in the system. I have to delete one" (Scarborough Pro vs Heartlake, 27 Jul 2025; both innings also labelled "Scarbrough Pro" batting).
- "I already uploaded two scorecard with this" (adding the 2nd innings photo of M-0825ED4D did not work; the same page was read with a different batting team each time).
- "I have both the innings here, then why is it saying that way" (M-CA36A6F1: both photos attached, but the card showed only Heartlake's innings and "Only one innings is on this photo").
- "AI is not reading data correctly, alert if mismatches" (live site: "Imran XI 219/8" shown as the result of Imran XI vs Heartlake, 6 Sep 2026; the home page "Recent results" said "Result not recorded" for the same game; an upload without a date listed under "January 0" with "MON undefined JAN").
- "Too many empty -, we should train to capture balls faced, 4s, 6s, dots, doubles etc and same for bowlers as well".
- "Today's free AI limit is used up ... use ollama".
- "Should say 1st innings or 2nd innings and should allow if I have only 2nd innings scorecard" (upload page on the live site).
- "I want the app like AI to do it better, so just train it".
- (Amit, Nov 7) "This looks like the same photo as 'image.jpg' (uploaded 2026-11-07). Duplicate uploads are not allowed" - "getting this error now on every upload after 6/sep/2026".
- (Amit, Nov 7) "Stats are not tallying in the clubs page after login, showing mismatch in matches in year wise and club wise stats of a player. Win rate of clubs in Ranking page is not giving accurate stats."
- (Amit, Nov 7) "I uploaded 1 innings and don't have another innings, is it possible to show this match in other clubs scorecards if the name of the club matches."
- (Amit, Nov 7) "AI should be accurate with batsman names, runs, balls faced, 4s, 6s, 1s, 2s, 3s; bowling stats overs, runs per overs, wickets, economy; AI should read the match date from scorecard or from its metadata".
- (Amit, Nov 7) "We need RAG in AI so that it learns the players names, uses aliases, their stats and less manual intervention"; "AI should try to map it with the existing players of that club"; "when we update at 1 place it should replace in other places while editing the scorecard manually"; "players in their profile page should be shown matching names (chuck, checkly, chukli, CJ) and asked to merge"; "captain name and man of the match"; "when we click on a player's name it should show the player's profile and stats in read only mode"; "download the prod data and use it to train AI".
- (Amit, Nov 7) "We need to have RAG in AI so that it learns the players names, uses aliases, their stats and less of manual intervention ... captain name and in the results should also identify the man of the match."
- (Amit, Nov 7) "When we extract the scorecard, AI should identify same name of players and if we update at 1 place then it should replace in other places while editing the scorecard manually. AI should try to map it with the existing players of that club so that we have less mismatch. How do we ensure that the player who registers with one name like CHECKLEY should see all his scorecards and totals with his match names like chuck, checkly, chukli, CJ ... players in their profile page should be shown matching names and asked to merge."
- (Amit, Nov 7) "When we click on players name it should show players profile and his stats in a read only mode." "You can download the prod data and use it to train AI."
- "getting internal server error on Azure, check the logs for errors" (log showed `sqlite3.DatabaseError: file is not a database` in signin).

### November 2026 local review of club, Player ID and stats issues
- Make sure the club-delete rule (only a club with no players and no matches can be deleted) is also enforced in the Admin Center.
- A club can be deleted only when it has no matches and no players. If a club has matches, scorecards or players, deletion is refused (409) and the user is told to disable it instead. (Earlier in the day I asked for multi-club players to keep their other-club data on deletion; that was rolled back in favour of this rule.)
- On the Clubs page I see 3 clubs to select but the Club Wise stats show 4 clubs with 0,0 data; the two lists must agree.
- When two clubs upload their innings of the same match separately and link them, it must become one match with both innings, the same Match ID for both clubs, visible in both clubs' scorecards, with club and player stats counted once (no duplicates).
- I played for Coca Cola and against TP Community so I should not see TP Community; if I played for both clubs at any time I should see both (Heartlake vs Coca Cola and Heartlake vs Amit CC show all clubs); fix for everyone.
- Review on local: innings linked but match not found; login shows only the primary club instead of every club played for (Heartlake plus Coca Cola and Amit CC); Player ID (1000) not visible, non-editable or saved in profile, club memberships and team selection; a scorecard not visible in Admin Center; a 2024 match with a score but no stats; Amit CC (played Heartlake in 2024) not auto-registering as a club; corrupted scorecard; team memberships showing only Amit CC after saving; inconsistent club pages; pages out of sync (normalise tables so every page reads the same data); club search not returning the club; default club showing only one club; online and uploaded matches must land in the same tables with player stats as total / yearly / club-wise.

### November 2026 club-specific player statistics
- Keep player rankings and statistics exclusive to their club. A player should appear for both clubs only when the scorebook shows them playing on each club's side; opponent batting, bowling and fielding figures must not be counted for the selected club. Include a played match in both clubs' My availability views when the signed-in player participated for that club, and make past-match availability read-only.

### November 2026 match scoring permissions
- Any signed-in player linked to either club playing a match can enter its live score, including a player on the opponent club when the fixture is owned by the other club. Only a captain of either participating club, a club admin of either participating club, or a superadmin can correct or remove saved balls, change an existing scorecard or line-up, or use scorebook edit mode. Enforce these rules in the APIs and show only the actions the signed-in user can use.

### November 2026 Scorecards club access
- The Scorecards page should open on the signed-in user's current club and show that club's matches and approved uploads. Only a superadmin may switch to another registered club or All clubs; enforce the club scope in the API as well as the page. Signed-out visitors retain the public scorecard view without a club selector.

### November 2026 unique visitor analytics error
- Fix the superadmin Unique visitors panel returning an Internal Server Error; hourly, daily, monthly, and annual visitor buckets must use the America/Toronto time zone.

### November 2026 club administration
- Add a dedicated Club Maintenance section in Admin Center to disable any club, re-enable it later, or permanently delete it. Keep disable/re-enable actions visible after the club details refresh. Put the other Admin Center tools in separate menu sections instead of displaying everything together. Disabling must preserve the club and its history while blocking its members from club access.

### November 2026 Clubs page visibility
- On the signed-in Clubs page, show a superadmin only their current club. Keep the full registered-club list available in Admin Center.

### October 2026 Azure infrastructure request
- Move production persistence from App Service SQLite to one free-tier Azure SQL Database PaaS database in Canada Central; keep test on SQLite; replace the East US Key Vault with a Canada Central vault; create no resources outside Canada Central.
- Delete the existing East US Key Vault named `testkeyvault179`.

### October 2026 local restart and Azure cutover request
- Restart the app against the local database, redeploy it to Azure, and ensure production uses Azure SQL and its Gemini API key to respond to scorecard extraction requests.
- Preserve and migrate the existing production data during the Azure SQL cutover; do not start with an empty database.

### October 2026 production Gemini deployment request
- Fix production, configure the solution to fetch the Gemini API key from Key Vault for scorecard extraction, and redeploy the latest code to Azure.

### October 2026 Home season label request
- Remove the duplicate “Season: 2026” badge from the signed-in Home page while retaining the “Season 2026” title.

### October 2026 Git sync and database ignore request
- Push the latest changes, then pull the latest remote changes; update `.gitignore` so local database files and sidecars remain untracked.

### October 2026 page title typography request
- Make titles smaller and more professional across all pages, including the signed-in Home welcome title.
- Reduce page-title font sizes to half of the previous size after the first sizing adjustment.
- Deploy the latest reduced page-title sizes to the existing Azure App Service.

### October 2026 latest Azure deployment request
- Deploy the latest code on `main` to the existing Azure App Service without packaging runtime data, uploads, or secrets.

### October 2026 match-management bug reports
- Show Heartlake's played 2026 fixtures after sign-in, even when a past match's scorebook has not been marked complete.
- Let a captain, club admin, or superadmin correct the match scorecard summary after match day without reopening past ball-by-ball scoring.
- Let the same authorized roles delete incomplete games, while preventing deletion of completed matches.

### October 2026 Azure refresh and redeploy request
- Refresh the latest code from `main` and deploy it to the existing Azure App Service.

### November 2026 Azure deployment request
- Deploy the latest local match-management fixes to Azure while preserving production data and the Key Vault Gemini configuration; keep local runtime data and secrets out of the deployment package.
- Deploy the latest live-style past-match scoring changes to the existing Azure site, including continued scoring through both innings, wide totals, and run-outs on wides and no-balls.

### November 2026 Heartlake Recent match and RBAC editing request
- Show the Heartlake–Afghan Eagles match in the signed-in Heartlake Home Recent results even though it has recorded scores/scorebook balls but still says Scheduled and TBD.
- Let users with the `score_matches` permission open that match in the editor from Recent; keep other users on the read-only public scorecard and enforce edits through the existing server-side RBAC checks.

### November 2026 post-match ball-by-ball correction request
- Let the assigned game captain, club admin, and superadmin correct or remove individual saved deliveries after match day.
- Use the same phone-first Quick Score scoreboard and delivery correction controls as a live match; keep all normal past-match views read-only and continue enforcing RBAC on the server.
- Keep the authorized Home and match-center entry points visible after refreshed assets and a local app restart; do not expose them to other users.
- Allow the authorized scorer to continue scoring an incomplete past innings with the standard live buttons, extras, wicket, batter/bowler selection, strike rotation, and save/retry flow.
- Keep the authorized live-style scoring workflow available through the active innings until the match has completed both innings; wide choices must include Wide through Wide +4 and allow a run out on wides and no-balls.
- Add retired-out scoring: the selected batter is out for the team, but it adds no runs or ball and is not credited to any bowler.
- Show a retired-out dismissal against the batter as "Retired out" / `RO`, not as a generic wicket; use the same wording in live alerts and do not include it in any bowler's figures.

### November 2026 retired-out Azure deployment request
- Deploy the latest retired-out scoring and scorecard-display changes to the existing Azure App Service without packaging production data or secrets, and preserve the Gemini Key Vault configuration.
- Deploy the follow-up clarification that retired out is not a wicket and that a returning batter loses the retired-out scorecard tag.

### November 2026 retired-out return request
- Allow a batter who retired out to return later in the same innings and resume with the runs and balls already recorded for them.
- Deploy the retired-out return feature to Azure.
- If two retired-out batters return to the crease, keep the innings open so they can continue scoring; a returned retired-out wicket no longer counts toward the all-out limit.
- Once a retired-out batter returns, show them as a normal not-out/batting player, remove their retired-out dismissal status, and allow their resumed scoring to count toward their existing figures.
- Clear the scorecard's retired-out tag when the batter appears again as striker or non-striker, even if a return marker is absent.
- Update the README to record all of today's retired-out scoring, return, and deployment changes.

### November 2026 retired-out clarification
- Treat retired out as a temporary batter departure, not a wicket: do not increase the team wicket total, include it in fall-of-wickets, or count it toward all-out. The batter may return and continue with their existing figures as a normal batter.

### November 2026 complete scorecard PDF request
- Add a direct PDF download for the complete public match scorecard, including batting and bowling details for all innings.

### November 2026 historical scorecard and availability request
- Let captains, club admins, and superadmins delete incomplete scorecards, but never completed match records.
- Keep played matches registered as fixtures, record a player's availability as Available when the scorebook confirms they played, and show historical scored matches in the scorecard archive with year and exact-date filters.
- Keep player and club records persisted in the database; do not turn completed historical matches back into upcoming fixtures.

### November 2026 played-club registration request
- Explain why Afghan Eagles is missing from player registration, and automatically register clubs and their recorded players from played games so they can be selected during registration.

### November 2026 incomplete live-match deletion request
- Show captains and admins a delete action in live scoring and on the live scorecard for an incomplete match, including one that has started but cannot be completed, while protecting completed matches and offering a path to start another match.

### November 2026 traffic, player identity, birth date, and audience request
- Give superadmins hourly, daily, monthly, and yearly visitor counts with the busiest time; show how many people are currently watching a live score.
- Give every registered user/player a stable unique Player ID that can link different display names and aliases to the same profile; let users optionally provide their date of birth at registration and edit it on their profile.
- Keep this README current, and confirm that `scripts/deploy_azure.sh` supports a manual ZIP deployment.

### November 2026 Afghan Eagles roster isolation correction
- Remove the false Heartlake memberships generated for Afghan Eagles players and prevent an unmapped primary team from inheriting the Heartlake club name.

### November 2026 numeric Player ID sequence request
- Use four-digit numeric Player IDs, assign `1000` to the superadmin, and increment other IDs from `1001`.

### November 2026 local restart script request
- Restart the local app so the current changes load, and add a reusable script for manual restarts.

### November 2026 neutral Player ID and registration list request
- Remove the CricketCanClubs brand prefix from Player IDs so IDs are globally neutral.
- Create a Player ID when a player is discovered in a played game and show it in registration's Not linked yet list.

### November 2026 club roster and stats isolation request
- Keep Afghan Eagles players and statistics out of Heartlake screens unless those players are explicitly members of Heartlake or their records come from Heartlake matches.

### November 2026 latest-code ZIP deployment request
- Review the Markdown documentation and current code, then deploy the latest `main` code to Azure App Service using `scripts/deploy_azure.sh`.

### November 2026 two-photo scorecard request
- (Amit, Nov 2) If an uploaded scorecard has only one innings on its photo, let the scorer upload the 2nd innings photo too and join it to the same scorecard.
- (Amit, Nov 3) The Upload page only let you take a photo; it must also allow choosing an existing photo from the phone.
- (Amit, Nov 3) Design: each match has a unique Match ID as the parent, with at least 2 unique innings IDs as children (one per side; a Test match has 4), so a missing innings scorecard is easy to see and to link to the match ID.
- (Amit, Nov 3 evening) Player ID 1000 not shown in profile and not saved; club memberships show only one club and saving the profile left only "Amit CC"; profile shows different clubs (Heartlake missing); year-wise / club-wise stats wrong (2024 score with no stats); club search finds nothing and only the default club shows; after sign-in a player must see every club they played for (Heartlake + Coca Cola + Amit CC). Review the database so every page reads the same data: unique club id (+ aliases), unique player id (player in many clubs), unique match id with 2 innings ids (Test: 4), online and uploaded matches feeding the same stats (total / yearly / club-wise). Roles: 1 superadmin (Amit only), 2 club admin, 3 captain, 4 player; delete only for club admins and the superadmin.
- (Amit, Nov 3, after deploying) The innings got linked but the match couldn't be found; and a player only sees their primary club on the club selection page, not other clubs they played for (Coca Cola, Amit CC).
- (Amit, Nov 3) Uploading the Heartlake vs Amit CC scorecards must register Amit CC as a new club (with its players), but it didn't.
- (Amit, Nov 2) The same match showed twice (each team's page: its own innings + the other team's total). Each match needs a unique Match ID with each innings tied to it; when duplicates are shown, suggest the Match ID so the other team can link their innings and complete the match.
- (Amit, Nov 1, re-checked Nov 2) Captains, club admins and superadmins must be able to edit a scored match: batters' names, the bowler, the teams. Delete must also remove wrong scorecards (not only incomplete ones), with the same roles.
- (Dhruvika, Nov 2, on Azure) Two photos of one match uploaded separately (one innings each) were flagged as duplicates and not linked. Either team may upload either innings (or one team both); they must be tied into one scorecard when the clubs, date and venue match.
- (Dhruvika, Nov 2) While there: the Scorecards date picker still stopped at the last uploaded card and Season missed the current year; Home threw "clubKey is not defined".

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
169. (Dhruvika, Oct 30) "Match not found." when saving line-ups for a new match.
170. (Dhruvika, Oct 31) Check everything again, especially scoring, before the real match.
171. (Dhruvika, Oct 31) A finished match's scorecard should not show the Live tab.
172. (Dhruvika, Oct 31) Check everything about scorecards.
173. (Dhruvika, Oct 31) Check everything again.
174. (Amit, Oct 31) Line-ups still said "Heartlake Cricket Club needs 2 to 11 players (now 21)".
175. (Amit / Dhruvika, Oct 31, Afghan Eagles match on Azure) In the 2nd innings the Score page showed the 1st innings players, the same bowler was typed twice (Parvez / Parwez) and the scorecard was wrong.
131. Find duplicate scorecards smartly with AI (Gemini, or Ollama offline), not only exact matches.

## Site analytics, player identity, and live audience

- Superadmins can open Admin Center's **Unique visitors** panel for distinct account/browser counts over the last 24 hours, 30 days, 12 months, and five years, with hourly, daily, monthly, and annual breakdowns. Buckets use `APP_TIMEZONE` (default `America/Toronto`); the busiest hour is summarized from the previous 30 days.
- The `tzdata` dependency supplies IANA zone rules on Windows and other hosts without a system time-zone database, so analytics can resolve `America/Toronto` correctly.
- Site visits are recorded only for successful HTML page views, with one pseudonymous visitor key per signed-in account or anonymous first-party browser cookie. IP addresses, names, and contact details are not stored in the analytics table. Traffic collection begins after this version is deployed; earlier visits are not backfilled.
- Every player/member has a four-digit numeric Player ID. The site superadmin is `1000`; other IDs are assigned sequentially starting at `1001`. Linked accounts share their player profile ID. Existing generated IDs are migrated on startup, IDs are retained across restarts and are not reused after deletion, and players found in played scorebooks receive an ID when added to registration options. The `Not linked yet` list displays each ID. Available IDs run through `9999`. Registration can link an unclaimed profile by Player ID or selection, and names entered during linking and profile aliases resolve to that same player. An ID already linked to another sign-in account cannot be claimed by registering again.
- Date of birth is optional at registration and on the player profile. It is stored as an ISO date, future dates are rejected, and DOB is omitted from public data and club-wide dashboard member lists.
- The public match page shows the current distinct viewer count while an innings is in progress. A viewer remains active for 45 seconds after their last scorecard poll; completed matches do not show a live count.

## Data model (Nov 2026 review)

One place for each kind of data; every page reads it through `load_store()` (SQLite `cricketclubapp.db`; `store_cache.json` / `dashboard_cache.json` are only caches of it).

| Data | Table(s) | Key | Notes |
|---|---|---|---|
| Clubs | `clubs` | `id` (e.g. `club-heartlake`) + `aliases` | Created at registration, from scored fixtures and from published scorecards |
| Players | `members` (+ `member_aliases`) | `id`; `player_id` = 4-digit Player ID (1000 = superadmin) | `app_users.member_id` links a login to a player |
| Player in clubs | `team_memberships` -> `teams` (`club_id`) | member + team | A player can be in many clubs; added from games played, by club admins, or by typing a registered club on the profile |
| Roles | `app_roles` (`role_id` 1-4), `app_users.role`, `app_user_club_roles` (per club) | | 1 superadmin, 2 club admin, 3 captain, 4 player |
| Online matches | `fixtures` + `fixture_scorebook_innings/batters/bowlers/balls` | Match ID `M-` + fixture id | Innings IDs `-I1`, `-I2` (Test `-I1`..`-I4`) |
| Uploaded matches | `archives` (+ `archive_scorecards`, `archive_performances`) | Match ID `M-` + archive id | Two pages of one match are joined into one archive (both photos) |
| Player stats | built by `build_combined_player_stats` from BOTH fixtures and published archives; saved in `member_summary_stats`, `member_year_stats`, `member_club_stats` | | Total and yearly = all clubs; club-wise = only the side the player played for |

Still two match tables (online `fixtures`, uploaded `archives`): both feed the same stats builder and show the same Match / innings IDs. Moving uploads into `fixtures` is the next step if wanted (a data migration).

## Database backups

Request (Amit, Nov 5 2026): "We need a backup plan for the DB, once we go live we cannot afford to lose the data" (after the Nov 4 production file was damaged on Azure Files).

- **Automatic, checked copies.** At start-up and every 6 hours (`CRICKETCLUBAPP_BACKUP_EVERY_HOURS`) the app copies the live SQLite file with SQLite's backup API (safe while it runs), runs `PRAGMA integrity_check` on the copy and only keeps it if it passes: `BACKUP_DIR/cricketclubapp-<UTC time>-<startup|scheduled|manual>.db`. `BACKUP_DIR` is `backups/` next to the live file (Azure: `/home/site/cricketclubapp/backups`, which survives restarts and deploys), or `CRICKETCLUBAPP_BACKUP_DIR`.
- **Kept:** the newest 48 copies (12 days at 6 hours) plus one per day for 30 days.
- **Off-site copy (recommended for go-live):** create an Azure Storage container and put its SAS URL (write permission) in the App Service setting `CRICKETCLUBAPP_BACKUP_BLOB_SAS`; every copy is then also uploaded there, so the data survives even if the App Service storage is lost.
- **Start-up health check:** if the live file fails `integrity_check`, the site admins get a notification straight away (and no damaged copy is kept as a backup).
- **Superadmin page `/admin/backups`** (Admin Center -> 🗄️ Database backups): live database health, every copy, **Back up now**, and **Download** for any copy. APIs: `GET/POST /api/admin/backups`, `GET /api/admin/backups/{file}`.
- **Before every deploy:** press **Back up now** (or it happens at start-up after the deploy anyway).
- **Restore:** stop the app (Azure: Stop the App Service), keep the damaged file aside (rename it `cricketclubapp.db.damaged-<date>`), copy the newest good backup over `cricketclubapp.db` (delete any `-journal` / `-wal` / `-shm` files next to it), start the app, sign in and check Scorecards / Clubs. At most the last 6 hours (or since the last "Back up now") are lost.
- Also (Nov 5): clubs from played games are registered before the first request instead of in a background thread - a background save could put an older copy of the data over a change that a request had just saved.

## Current behavior summary

- `2026 Summer Season` is the running CricketClubApp season shown in the site header.
- Historical archive scorecards are stored separately from live fixtures.
- Reviewed historical scorecards count as confirmed historical match history in chat/stat answers.
- Chat uses persisted member names, full names, aliases, memberships, fixtures, archives, and rankings as its source of truth.
- The landing page now starts with local registration, primary-club selection, club search, player search, and a followed-player watchlist.
- The selected primary club drives the landing-page focus for upcoming events, upcoming matches, and club stats.
- The app now includes dedicated multi-page flows for `Registration`, `Sign In`, `Club Selection`, `Season Setup`, `Player Availability`, and the club `Dashboard`.
- Club selection shows the selected or primary club first and keeps the rest selectable.
- The signed-in `/clubs` page limits superadmins to their current club; they manage and select other registered clubs through Admin Center. The Admin Center club selector continues to include all registered clubs.
- The club dashboard is now club-focused and removes the in-page club picker so it reflects the selected club only.
- Season setup stores fixtures with their own season year so `2026` and `2027` schedules can coexist.
- Player availability is shown against the selected club's active season fixtures after login. Historical scorebook appearances are persisted as Available and displayed read-only in My availability.
- The clubs page now shows a player snapshot plus year-wise and club-wise summary tables using cached SQLite stats.
- The clubs page Player Snapshot is resolved from the signed-in player's canonical `member_id`, and it should not fall back to another roster member.
- Player profile club memberships are deduplicated before display so the same club does not appear multiple times.
- Summary milestone counts use `25+`, `50+`, and `100+` bands.
- Player availability is now set per scheduled game, not as one season-wide toggle.
- The player profile is the cross-club career view, while the club dashboard stays club-local.
- Club rosters use explicit club/team affiliations as the source of truth; an account's selected club cannot add someone with an unrelated saved team to that club. A primary team with no club mapping is not assigned to Heartlake by default. Club scorebook selectors use the focused club roster and current match lineup, not the global player directory.
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
- Registration options also reconcile clubs and players from scored fixtures, so an opponent and its recorded scorebook players can be selected without a separate manual club setup.
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

From the project root on Windows, start the app against the local SQLite database:

```bash
python app\main.py
```

The server uses `app\data\cricketclubapp.db` by default and listens on port `8090`. If using the repository virtual environment:

```bash
.\.venv\Scripts\python.exe app\main.py
```

Open `http://127.0.0.1:8090`.

To restart the local app and wait for its health endpoint, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_local_app.ps1
```
The script checks that the port listener is this app before stopping it. Set `CRICKET_APP_PYTHON` to override the interpreter; logs are written under `%TEMP%`.

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

- Production Gemini scorecard extraction uses the App Service system-assigned managed identity, the Key Vault Secrets User role on `cricketcanclubs-prod-kv`, and the `GEMINI_API_KEY` application setting as a versionless Key Vault reference to `GEMINI-API-KEY`. Azure resolves the reference into the environment variable read by `app/ai_vision.py`; do not add the key to `.env`, source, or deployment artifacts. After changing the secret, verify the reference and `GET /api/scorecards/reader`.
- Production was redeployed on 2026-10-28. `/api/health` returned `ok`, `/api/scorecards/reader` reported Gemini, and a synthetic scorecard returned the expected 17-run innings using the Key Vault secret and the application's extraction code. This Gemini configuration does not connect the app to Azure SQL: production continues to use its persistent SQLite database until the separately documented data migration is complete.
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

- Admin Center uses a section menu for Club Maintenance, Overview, Unique Visitors, Scorecard Tools, Archives, Audit Log, and Fixtures. Club Maintenance opens by default and holds the club selector, disable/re-enable actions, permanent deletion, and roster cleanup.
- Superadmins can disable a club from its Admin Center detail card after typing its exact name. A disabled club remains stored with its match history, is hidden from public and regular-user club choices, and its members cannot select or use it. Superadmins can still select the club in Admin Center and re-enable it. Permanent deletion remains a separate destructive action.
- The client-rendered Club Maintenance card must show the club's active/disabled status and the matching Disable club or Re-enable club form after each club load, alongside the permanent-delete form.

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
- The ZIP includes the product and LLM documentation from `MD/`; on systems without `rsync` or `zip`, the script uses `cp` and Python's ZIP module. Set `PYTHON_BIN` when the default `python3` command is unavailable.
- Manual ZIP deploy command: `DEPLOY_APPROVED=yes PYTHON_BIN=python3 bash scripts/deploy_azure.sh` (use the installed Python executable for `PYTHON_BIN` where needed). The script builds the ZIP, deploys it with Azure CLI, and restarts the App Service.

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
- **Page titles** use a shared, compact Inter-based heading scale in `static/sports-system.css`; Home, Rankings, Sign In, Quick Score, and pricing overrides follow the same responsive scale.
- **Sign In / Register** pages: `static/signin.css`, `static/register.css` (Register is a 3-step card).
- **Public Clubs page** for signed-out visitors: `GET /clubs` serves `public_clubs.html` (`GET /api/public/clubs`).

### Digital scorecards (`/scorecards`)
- `GET /api/public/scorecards?date=&club_id=&year=` lists approved uploaded scorecards and past played fixtures, newest first; `GET /api/public/scorecards/{id}` returns one Cricinfo-style card (batting, bowling, extras, did-not-bat, match details, original photo URL when uploaded). Year and exact game-date filters include every season represented in the archive.
- Pages: `static/scorecards.html/js` (list grouped by month, date picker with "closest dates", club and season filters) and `static/scorecard.html/js` (innings tables + "Original scorecard" photo tab). Styles: `static/scorecards.css`.
- Signed-in players default to their current club and the API returns only scorecards involving that club, including a shared fixture where the scorebook identifies the club as a playing side. Only superadmins can change the club filter or select All clubs; their selector lists every registered club. Signed-out visitors retain the public all-scorecards view without a club selector.
- Archived scorebook fixtures retain their fixture and roster records in the database; no fixture duplication is created to populate the archive. Captains, club admins, and superadmins can delete incomplete scorebook cards, while completed matches return **409** and remain intact. Those authorized roles can also delete unapproved/incomplete archive uploads from their club; approved scorecard uploads are protected.
- `GET /api/auth/options` idempotently adds missing clubs from scored fixtures and creates/links members from each innings' batting, bowling, and fielding scorebook records. Upcoming unscored fixtures do not create registration clubs; existing player club memberships are preserved.
- Archive review uses the same shared `scorecard.js` renderer and `scorecards.css` for a digital snapshot beside the editable extraction JSON; the uploaded original image is rendered directly in the review panel, without displaying its URL. HEIC/HEIF originals are converted to browser-compatible JPEG previews while preserving the original upload; an original-photo tab remains included in the snapshot. The three panels sit side by side on wide screens and stack on phones. Pending previews are returned only from the superadmin-protected Admin Center queue.
- Scorecard image extraction uses local Ollama vision when a supported model is installed. It submits the full page plus enhanced header, batting-table, and bowling-table crops and writes the model's innings, batting, bowling, dismissal, extras, and match fields into the review JSON. Vision models are auto-detected (including tagged Ollama names); `ARCHIVE_VISION_MODEL` can select one explicitly. On Windows, install Ollama, pull `qwen3-vl:8b`, verify it appears in `http://127.0.0.1:11434/api/tags`, then use **Re-extract** on a pending archive. Re-extraction clears stale extraction JSON before regenerating it. If no local vision model or OCR tool can read the image, the review summary says so and keeps the item pending; all AI-generated figures still require admin verification.
- Data comes from the best available copy of each archive's extraction (reviewed JSON, template, imported performances, draft scorecard). Missing figures show as "–".
- Public match scorecards (`/live/{id}` and `/public/match/{id}`) provide a **Download complete scorecard (PDF)** action. The generated PDF includes each scored innings' full batting and bowling tables, extras, totals, did-not-bat list, and fall of wickets. It downloads directly without a browser print dialog. Test the PDF builder, download response, content headers, and missing-match response with `python -m unittest tests.test_local_qa.UnitQATests.test_public_match_scorecard_pdf_is_a_downloadable_complete_pdf`; check the action at 390px and laptop width.
- Captains, club admins, and superadmins see **Delete incomplete match** on a started or unstarted unfinished `/live/{id}` scorecard. It uses the fixture deletion API's role checks and completed-match protection, then offers a direct link to start another match.

### Home pages
- **Public home** `/live` (`static/home.js`, `static/home.css`): match strip (Live / Results / Upcoming), off-white banner with featured match, latest scorecards, recent results, coming up, join banner.
- **Signed-in Home** `/dashboard` (`static/dashboard_home.js/css`, only on the overview): welcome card with quick actions, match strip, latest scorecards, and an **AI Assistant** card at the bottom. Panels that duplicated the navbar (scoring keypad, main menu, registration form) are hidden on Home.
- The signed-in Home hero shows the selected season year once in its title; the duplicate season badge is omitted.
- **Matchday tile**: if there is no upcoming fixture it shows the **last match that has a score** (both totals + result) instead of an old date (`renderLastMatchHero` in `app.js`).

### Quick Score (`/score`)
- Files: `static/quick_score.html/js/css`. APIs: `GET /api/quick-score/fixtures`, `GET /api/quick-score/{match_id}`, `POST /api/quick-score/start` (creates today's fixture), plus the existing `POST /api/matches/{id}/scorebook/setup`, `POST .../scorebook/ball` and `DELETE .../scorebook/ball` (undo).
- Captains, club admins, and superadmins can delete unfinished matches, including started scorebooks, from Quick Score. The server verifies role and completion status; after deletion the page offers **Start a new match** and **View fixtures**.
- Flow: pick today's match (or "Start a match now") → choose batting side, openers and bowler → score with big buttons `0 1 2 3 4 6 / Wd Nb Bye LB / W / Undo`.
- Strike rotates automatically on odd runs and at the end of each over; after 6 legal balls it asks for the next bowler; W opens a pop-up for how out, fielder and the new batter; 2nd innings shows the target and required rate.
- Any signed-in player linked to either participating club can enter live balls. Score corrections, undo, saved scorecard changes, line-up changes after initial setup, and historical edit mode require a participating club captain, club admin, or superadmin. The server checks both club memberships and roles; the fixture appears in the opponent club's Quick Score list as well.
- **Retired out** is a temporary batter departure, not a wicket. It adds no runs, ball faced, legal ball, bowler credit, or team wicket; the batter can return later with their existing figures.
- The AI Live Scorer recognizes “retired out” and prompts for the batter and replacement without adding a run, ball, or wicket.
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

### Club-specific player stats (Nov 2 2026)
- Club rankings, selected-year Home rankings, and club Stats are calculated from the scorebook innings for the selected club. Batting counts only when that club is batting; wickets and catches count only when that club is bowling/fielding. Highest scores and milestones use the same team-side filter. The combined fixture performance list contains both teams and must not be used as-is for club rankings.
- Players with appearances for two clubs retain their stats for each club, based on the side they played on in each scorebook. For old fixtures without scorebook innings, only known club members' manually entered performances are included. A club also receives its players' scorebook stats from an opponent-owned fixture when its team is recorded as batting or bowling; fixture ownership remains with the original club.
- The dashboard's player summary and season-by-season rows are scoped to the selected club as well. The focused-club snapshot uses the fresh filtered rankings instead of stale materialized top-batter rows. Cross-club history remains available in player profiles, where memberships are shown separately. A club dashboard also includes an opponent-owned match when its scorebook records the focused club playing, while retaining the original fixture owner. Signed-in Rankings uses the focused club roster; public Rankings remains global.
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
- One-tap pop-ups (no Save button; `openSheet` in `quick_score.js`): next bowler at the end of an over (shows the over's runs / wickets / "maiden!" and each bowler's figures; the bowler who just bowled is greyed out), byes / leg byes (1 2 3 4), no balls (No runs, +1 ... +6), and wides (Wide through Wide +4). Wides and no-balls can also be recorded as run-outs.
- Wicket in 2-3 taps: How out (Bowled, Caught, LBW, Run out, Retired out, Stumped, Hit wicket) -> fielder for caught / stumped / run out (the bowler is marked, "Don't know · skip"), for a run out also who is out and runs completed -> next batter (only players still to bat; "No more batters (all out)"). Retired out lets the scorer choose either current batter, counts one team wicket, and records no run, ball faced, legal delivery, or bowler credit.
- Fix any ball: tap a ball in "This over" -> pick what really happened (runs, wides, no balls, byes, leg byes). The ball is replaced in place (`POST /api/matches/{id}/scorebook/ball` or `/api/guest/matches/{id}/ball` with the ball's `id`; `_apply_ball_edit` in `main.py` keeps its over, ball number and time; a fixed ball sends no new alerts; a finished innings opens again if the fix means it isn't finished). For the last ball there are also "It was a wicket" and "Delete this ball". Strike is worked out again when the last ball is fixed.
- Line-ups: "Select all" / "Clear" for the club's players, "Use Player 1-11" when the other team's names aren't known, and lists pasted from WhatsApp are cleaned ("1. Ravi (c)" -> "Ravi"; also for guest matches).
- Celebrations (`static/celebrate.js`): FOUR!, SIX!, WICKET!, FIFTY! and HUNDRED! pop up with confetti and a short phone buzz on the Score page, and on the public live page (`/live/{id}`), which now refreshes by itself every 15 seconds while the match is live (the first load never celebrates old balls). The banner never blocks taps; reduced-motion phones get a plain banner.
- Tested in the cloud workspace on a copy of the database at phone size (412 x 915): a full guest match (pasted line-up, picking openers, four, byes, caught, next bowler, fixing a 2 into a 4, no ball +4, run out of the non-striker) gave the right totals and strike, the public page celebrated a six from another phone, and fixing a club match ball kept its place.

### Post-match ball-by-ball correction (Nov 1 2026)
- Authorized match scorers can open `/score?match={id}&edit=1` from Home's Recent results or the match-center scorebook lock message. This opens the same phone-first scoreboard, all-overs view, and tap-to-fix flow used for live scoring.
- The assigned game captain, club-scoped users with `score_matches` (including club admins), and superadmins are checked server-side through `_require_match_scorer`; unauthorized users cannot use the `edit_mode=true` scorebook write routes.
- Edit mode follows the active innings with live scoring controls until both innings complete; after the first innings ends, the scorer can start the second innings without leaving edit mode. The authorized scorer can select either innings to fix or remove saved deliveries, undo the last ball, and append deliveries to an unfinished innings. Wide offers Wide and Wide +1 through Wide +4, and both wide and no-ball dialogs support a run out with the usual batter, completed-runs, and fielder choices. Extras and completed runs update totals and strike correctly. Saved edits recalculate summaries/results and reindex deliveries; historical changes do not send live alerts. AI Scorer is not offered in edit mode. Regular past-match routes remain locked.
- Retired out is available in live scoring and authorized edit mode. It counts as a team wicket, but adds no runs, batter balls faced, legal balls, or bowler attribution. Display `RO` / "Retired out" against the dismissed batter, not a generic wicket, and use the same wording in live alerts; exclude retired-out deliveries from bowler figures, including legacy records with bowler names. The next-batter picker lets the scorer bring a retired-out batter back into the innings; their existing runs and balls remain on the same scorecard row. On return, clear that batter's retired-out dismissal status and show them as batting/not out; remove them from the retired-out return choices. Persist the incoming batter with the delivery so the live scorer, public scorecard, and server agree after refresh; SQLite gets a backward-compatible nullable `new_batter` column.
- A returned retired-out wicket remains in the scorebook's wicket total, but no longer counts toward the all-out limit or wickets remaining in the winning margin. This lets two returned retired-out batters continue scoring; normal innings limits and other dismissals still apply.
- Display retired out as `RO` / "Retired out" against the dismissed batter, not as a generic `W` / "Wicket"; live alerts use the same retired-out wording. Exclude it from every bowler's figures, including scorebooks saved before the API began clearing the bowler field.
- How to test: sign in as the assigned captain, club admin with scoring access, or superadmin; open an unfinished past match with `?edit=1`, append runs/extras or a wicket, refresh and verify the saved score and innings state; after a retired-out dismissal, choose that batter at a later wicket and verify their previous runs and balls remain, their status is batting/not out, and their retired-out dismissal is cleared; return two retired-out batters and confirm the innings stays open and accepts further runs; confirm an ordinary past-match write remains refused and unauthorized edit-mode writes return 403. Check the scoring controls at 390px and laptop width.

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
- (Nov 2) Past fixtures with saved scorecard values or scorebook balls are included in public fixture data and Recent results even if their status/result fields are stale. Signed-in Home shows an **Edit scorecard** link only when `/api/auth/me` grants `score_matches` for the member's current club; the editor's existing server checks remain authoritative.
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

### Past matches, scorecard corrections, and incomplete-game deletion (Oct 2026)
- A match whose date is before today (Toronto time, `_current_local_date`) keeps live ball-by-ball scoring, availability (`/api/matches/{id}/availability`, `/api/player/availability`), the playing XI (`/lineup`), performances, commentary, and AI Assistant score/availability tasks locked. These actions continue to return **403 "This match was on … Past matches are locked"** (`_require_not_past` in `main.py`).
- The assigned match captain, club captains, club admins, and superadmins may edit the scorecard summary after match day. This does not unlock ball-by-ball scoring or change a past match's status. The match-centre selector keeps an authorized past match selected so its scorecard can be corrected; the performance and commentary forms remain locked.
- The signed-in Fixtures page retains past matches with scorecard runs or recorded scorebook balls even if their status is still in progress. Past unplayed fixtures remain hidden there, and historical matches are not shown as upcoming. Scored past fixtures also appear in the digital scorecard archive with date and season filters.
- Club captains, club admins, and superadmins can open Matches / Season Setup to delete incomplete fixtures even when they cannot create or edit schedules. Fixture-scoped permissions are returned by the API; completed games are protected and return **409**.
- When a scorebook confirms a linked member batted or bowled in a past match, My availability records that member as **Available** and shows the historical fixture read-only. This corrects historical availability from the match record without making it editable after match day.
- Past fixture details (date, opponent) remain editable only by club admins and superadmins.

### How to test (Oct 2026)
1. Restart the app. Open Availability: today's/future fixtures can be updated; a past scored match the signed-in player appeared in shows read-only as Available. Open Fixtures: no past "Scheduled" games; the fixture manager shows "Past fixtures (N)" folded.
2. Open an authorized past match in the match centre: scorecard summary fields can be saved, while scorebook, performance, commentary, availability, and playing-XI actions remain locked. A player without `score_matches` must receive **403** if attempting a scorecard edit.
3. Open Fixtures while signed in: an older match with scorecard runs or scorebook balls stays visible even if its status is not `Completed`; a past unplayed fixture is hidden.
4. In Matches / Season Setup, delete an incomplete fixture as a captain, club admin, and superadmin. A completed match must remain and the API must return **409**.
5. Open `/scorecards`: verify past scorebook matches appear alongside approved uploads. Filter by a historical season and an exact date; delete an incomplete scorecard as an authorized role and verify a completed scorecard has no delete action.
6. Tap **✨ AI Assistant** and try: "Add a match vs Old Boys XI on Saturday at 2pm" → Confirm; "Ask everyone for availability"; "Mark me available for the next match"; "Who is available for the next match?"; "Pick the best XI for the next match"; "We are 85/3 after 12 overs" (needs a match today, e.g. from Quick Score). Each shows a plan with Confirm / Cancel.
7. Ask a question ("How is Amit S doing?"): it is answered by the LLM (the header says which model) or the built-in data assistant when Ollama is off.

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

- 2026-11-11: Admin Center Name matches now has three actions for each pair: "Merge into <older> (older)", "Merge into <newer> (newer)" and "Not the same player". `POST /api/admin/name-matches/merge` takes an optional `keep_member_id` (must be one of the two players). New `POST /api/admin/name-matches/reject` saves the pair in the new table `app_name_match_rejections`, and `GET /api/admin/name-matches` hides saved pairs. Tests: `tests/test_player_merge.py` (`test_admin_can_keep_newer_record_when_merging`, `test_admin_keep_choice_must_be_one_of_the_pair`, `test_rejected_name_match_is_saved_and_hidden`). Bumped `admin_center.js?v=20261111d`.

- 2026-11-10: Admin Center merge requests: Reject was already on each request card (`data-merge-request-decision="reject"`, `POST /api/admin/merge-requests/{id}/decision`). Added test `tests/test_player_merge.py::test_admin_can_reject_merge_request` (reject keeps both players, marks the request rejected and removes it from the pending list). Bumped `admin_center.js?v=20261111c` so browsers load the current script.

- 2026-11-10: Match threshold is now "at or above 75%" (`score >= PLAYER_MERGE_SUGGEST_MIN_SCORE`, 0.75). The club card, merge requests, candidate details and the upload name check all use it. Any uploader sees the upload name check match; only reviewers get the merge buttons. Test: `tests/test_player_merge.py::test_candidate_score_is_75_percent_or_more`.

- 2026-11-10: AIDuplicateEngine (`app/ai_duplicate_engine.py`, class `AIDuplicateEngine`; was `player_match.py` / `MatchEngine`). Replaces the name-only `_members_match_score`. It scores a pair of members as `0.7 × name + 0.3 × club`, with a reason for each part. Name evidence uses every identity name (name, full name, aliases): exact = 1.0, name plus 1-2 letter initial = 0.9, otherwise `SequenceMatcher` ratio. Club evidence uses primary and secondary clubs (`primary_club_id`, `team_memberships`, `club_memberships`): same primary club = 1.0, any shared club = 0.6, club missing on one side = 0.3, different clubs = 0.0. A veto stops two different people being merged: when both names bat as different names in the same archived match, the pair scores 0. It is used in: the club card (`GET /api/player/merge-candidates`, `GET .../details`, returning `match_percent`, `reasons` and `recommended`), merge requests (`POST /api/player/merge-requests`), the upload name check (`_card_name_matches`, the card name is scored as a pseudo-player in the uploader's club), and Admin Center Name matches (`GET /api/admin/name-matches` adds `ai_match_percent` and `ai_reasons` to each group; the name rule still picks the groups, so no pair is hidden). Threshold stays at `PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.75, strict "over 75%". Nothing merges automatically. Tests: `tests/test_player_merge.py::test_candidate_score_needs_more_than_75_percent`, `::test_engine_suggests_initial_match_only_with_club_evidence`, `::test_engine_uses_secondary_clubs`, `::test_engine_vetoes_two_names_batting_in_the_same_match`. Versions bumped to `dashboard_home.js?v=20261111b`, `dashboard_home.css?v=20261111h` and `admin_center.js?v=20261111b`.
- 2026-11-10: Merge suggestion card (club page) now asks the player to choose which record to keep: "Merge into older record" or "Merge into newer record" (`POST /api/player/merge-requests` with `keep` = `older` or `newer`, default `older`; any other value returns 400). The kept record id is saved in `app_merge_requests.keep_member_id` (new column, added by migration) and passed to `merge_members_in_store(..., keep_id=...)` when an admin approves. The threshold is now 50% (`PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.5, rule `score > 0.5`). Tests: `tests/test_player_merge.py::test_candidate_score_needs_more_than_50_percent`, `::test_player_can_choose_which_record_survives`.
- 2026-11-10: Merge suggestion card (club page) now has a "Not me" button. It saves the choice in `app_merge_suggestion_dismissals` (`POST /api/player/merge-suggestions/{target_member_id}/dismiss`, idempotent) and the record is then left out of `GET /api/player/merge-candidates`. A rejection is permanent for that player and is not visible to admins. Each card shows the full name, clubs, a career strip (matches, runs, wickets, high score) and a "View details" panel. That panel loads `GET /api/player/merge-candidates/{target_member_id}/details`: aliases, clubs, and up to 10 recent batting rows (date, club, opponent, R(B), W, C) matched by any of the player's known names. It only serves records that are valid suggestions for the caller. Merge-request validation (`POST /api/player/merge-requests`) now uses the same 50% score, so any card shown can be requested. Styles are in `dashboard_home.css` (`.merge-*`). Tests: `tests/test_player_merge.py::test_rejected_suggestion_is_saved_and_hidden`.
- 2026-11-10: Player merge card moved from the profile page to the club page (dashboard overview). It shows only when another member's name is more than 50% similar, or the player has an earlier request. The candidates endpoint scores names by `SequenceMatcher` ratio (`_members_match_score`), and each card shows its match percent. Admin Name matches still uses the 0.85 rule. Tests: `tests/test_player_merge.py::test_candidate_score_needs_more_than_50_percent`.
- 2026-11-10: Member merge (admin). Name Matches now has a "Merge into" button per duplicate. `POST /api/admin/name-matches/merge` (`manage_players`; each member must pass `_reviewer_can_decide`) runs `app/player_merge.py::merge_members_in_store`. The older record (earlier list index) survives. References to the removed member (`member_id`, `heartlake_captain_member_id`, `selected_playing_xi_member_ids`, `*_member_id(s)`) are rewritten to the survivor. Scorecard `player_name` text is never changed, so historical names stay as written. Aliases and club links are folded into the survivor. A merge is refused when both members appear in one top-level record (would double count). Login links (`app_users.member_id`, `app_followed_players`) move to the survivor. Each merge is saved in `app_member_merges` with a store snapshot. `POST /api/admin/member-merges/{merge_id}/undo` (superadmin only) restores it and returns 409 if the store changed after the merge. Stats tables are rebuilt on save. Tests: `tests/test_player_merge.py`.
- 2026-11-10: Name matching. `_names_look_same` (main.py) treats a name plus a 1-2 letter initial ("Bim" / "Bim B", "Amit" / "Amit S") as a match, since the similarity ratio was below 0.85 for short names. Used by Name matches (`GET /api/admin/name-matches`) and merge requests. Merges already add the removed name to the survivor's aliases. Matching is also alias-aware: `_identity_names` (normalized name, full name and aliases) and `_members_look_same` compare every identity name of each member, so "Bim B" in an alias matches a member called "Bim". Similar pairs are bucketed by 2-character prefix to keep the scan fast. Stats survive a merge because scorecard rows are rolled up through aliases, not by name: Bim 20 runs plus Bim B 30 runs gives 50 runs. Tests: `tests/test_player_merge.py::test_aliases_count_for_name_matching`, `::test_stats_add_up_after_merge_through_alias`. Admin Center `refreshAll` also loads Name matches, Merge requests and Name claims before the slow club dashboard call. Tests: `tests/test_player_merge.py::test_name_plus_initial_counts_as_a_match`.
- 2026-11-10: Player merge requests. On the club page (dashboard overview, `index.html` / `dashboard_home.js`), `#clubMergeCandidates` lists other members whose name is more than 50% similar (`GET /api/player/merge-candidates`, `match_percent`; scored by `_members_match_score`, threshold `PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.5). The card stays hidden when there is no such match and no earlier request. It sends a request (`POST /api/player/merge-requests`, table `app_merge_requests`, one pending request per pair). The request does nothing by itself. A reviewer who passes `_reviewer_can_decide` approves or rejects it in Admin Center > Name matches (`GET /api/admin/merge-requests`, `POST /api/admin/merge-requests/{id}/decision`). Approve runs the same merge as above. Note: the candidate list shows other members' names, player IDs and club names to the requesting player. The target player is not asked to confirm yet. Tests: `tests/test_player_merge.py::test_player_merge_request_is_decided_by_admin`, `::test_candidate_score_needs_more_than_50_percent`.
 to Admin Center (between Archives and Audit Log). It shows the "Name matches" card, which calls `GET /api/admin/name-matches` (needs `manage_players`). That endpoint groups members with the same normalized name (`exact`) or a similar name (`SequenceMatcher` ratio of at least 0.85, compared only within names that share their first two characters). Each member shows its player ID and club names from `club_memberships`. Club admins and captains see a group only when every member is in their clubs; superadmins see all. It only reads data; no member, alias or claim is changed. Tests: `test_name_matches_is_read_only_and_restricted_to_managers` in `tests/test_player_claims.py`. Also added in-memory caching for the sign-in stats, the LLM status probe (30 s TTL) and the store/dashboard clone (pickle instead of deepcopy) to speed up local page loads.

- 2026-11-10: Scorecard upload name check. After an upload, names on the card (batting and bowling) are compared with player names and aliases (`_card_name_matches` in main.py, using `_members_match_score`). One match is "recognised" (for example "Amit S" as an alias of Amit Sethi). Two matches are "possible duplicate" and the older record is listed first. Threshold: the same `PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.75 as the club card, with a strict "over 75%" test. The upload response and `GET /api/scorecards/{id}/preview` return `name_matches`, and the upload message gets a "Name check:" sentence. The preview (`scorecard.js` `nameMatchesHtml`) offers "Merge into older/newer record" only to users who pass `_reviewer_can_decide` for both players, otherwise "Ask a club admin"; "Not the same, ignore" hides the item in the page only. `POST /api/scorecards/{id}/name-merge` (`ScorecardNameMergeRequest`) merges only a current match on that card, returns 404 otherwise and 403 when the user cannot decide both players. Nothing merges automatically. Styles: `.sc-name-match` in `scorecards.css`. Versions bumped to `scorecard.js?v=20261111a` and `scorecards.css?v=20261111a`. Tests: `tests/test_player_merge.py::test_upload_names_flag_aliases_and_possible_duplicates`.
- 2026-11-10: Match threshold set to 75% everywhere. `PLAYER_MERGE_SUGGEST_MIN_SCORE` = 0.75 (strictly over) now drives the club-page merge card, its merge request check, the club-page text in `index.html` and `dashboard_home.js`, and the upload name check. The 80% and 50% entries above are history. Initial-only names such as "Bim" / "Bim B" (score 0.75) are not "over 75%"; they still match in Name matches through `_names_look_same`. Tests: `tests/test_player_merge.py::test_candidate_score_needs_more_than_75_percent`.
- 2026-11-10: Duplicate-player Phase 0. Player name claims no longer merge same-name members automatically (the old `player_claim_name` removed member rows and copied club links). A claim now creates a pending row in `app_name_claims` (schema in `ensure_auth_schema`, `main.py`) and changes nothing else. Superadmins decide every claim; club admins and captains decide claims for members of their own club (`_reviewer_can_decide`). Approve adds the claimed name as an alias only, and refuses if another member already uses that name. Reject records the decision only. Endpoints: `GET /api/admin/name-claims` and `POST /api/admin/name-claims/{claim_id}/decision` (both need `manage_players`). Admin Center shows a "Name claims" card (`admin_center.js`). Name normalization is one function, `cricket_store.normalize_name`, which now also collapses inner whitespace; `main.py` uses it. Sign-in, scorecards, statistics, Player IDs and Azure are unchanged. Tests: `tests/test_player_claims.py`. `tests/test_local_qa.py` now runs `gc.collect()` before deleting its temp copy, because Windows keeps the SQLite file locked otherwise.- 2026-11-09: Live match page and fixtures from published scorecards: when a published scorecard is linked to a past fixture (same club, date and both teams, the same rule as the Scorecards link), the fixture takes its result and innings scores (`_sync_fixture_results_from_scorecards` in `main.py`). It runs when a scorecard is approved and at startup (backfill), and never overwrites a fixture that already has scores. A scorecard with only one side's total (e.g. `a-fa879005`, Coca Cola XI's innings has no total) is not copied, so no result is invented. The link itself now uses the same team-name rule as the sync (`_same_team_name`, so "Coca Cola" matches "Coca Cola XI"); it was exact before and missed 12 Jul vs Coca Cola XI (`a-d74a39dc`). Audit on the live DB copy: 2 of 17 fixtures filled (12 Jul, 6 Sep); 5 Jul, 26 Jul and 23 Aug are linked but their scorecards lack the other side's innings; the rest have no published scorecard.
- 2026-11-09: One scorecard layout everywhere: the innings markup (batting and bowling tables, dismissals, runs/wickets headers, "Did not bat") now lives in `scorecard_view.js` (`window.CricketClubAppScorecardView`). The uploaded/published page, the Admin Center preview and the live page's published fallback all use it, so `/live/<fixture>` and `/scorecards/a-...` show the same innings. Player names link to `/players/<id>` on the live page too: `_public_match_payload` returns `match.player_keys` (lineup name -> player id via `_lineup_player_keys`), and `public_match.js` uses `nameLink` for batters, bowlers, yet to bat and key players. `scorecard.html` and `public_match.html` load `scorecard_view.js` first (`scorecard.js` v20261109b, `public_match.js` v20261109b). Needs an app restart; not yet verified in a browser.
- 2026-11-09: Fixed the "Loading scorecard…" hang on `/scorecards/a-...` (a bad edit had removed `scorecardMarkup`'s return; `scorecard.js` is now v20261109c). Player links on the live page also work when the match has no lineup: `_public_match_payload` resolves each name on the linked published card to a registered player (`match.player_keys`), and `renderPublishedScorecard` passes those keys to the card rows (`public_match.js` v20261109c). Verified in the browser at `/live/2026-08-23-carl`: 22 names link to `/players/<id>`, no horizontal overflow at 390px.- 2026-11-09: Live match page and its linked published scorecard now show the same Match ID and innings layout (Live: published card code, not the fixture id)., `a-fa879005`): the page showed "Upcoming" and an empty Scorecard tab although the published scorecard has Heartlake's innings. It now shows that published scorecard (both innings, batters and bowlers) and the status is "Completed" (`_published_scorecard_for_fixture` in `main.py`; `renderPublishedScorecard` in `public_match.js`). The result stays "Heartlake Cricket Club 215/9 in 35 overs" until Coca Cola XI's innings is on the scorecard.
- 2026-11-09: Score format is the same everywhere: fixture scores (Home "Recent results", fixtures, live page) now show "runs/wickets" like the archive card ("215/9"), not bare runs ("215"). `_side_score_text` in `main.py` builds it from the scorecard's runs and wickets; wickets are left out when all out (10), as in `_scorecard_from_archive`.
- 2026-11-09: Scorecard styling and score format match across the published scorecard and the live fallback: the live fallback's innings headers are now clickable (▾ toggle, last innings open) like `scorecard.js` `inningsBlock`; `.pm-inn:not(.open) .pm-inn-body` hides closed innings in `public_match.css` (previously only `scorecards.css` did); dismissals sit on their own line (`.pm-dismissal`). Innings headers and ball-by-ball headers show "runs/wickets" (e.g. "215/9"), wickets left out at 10, as on Home and fixtures. Asset versions bumped (`public_match.css` v20261110b, `public_match.js` v20261110a, `scorecard.js` v20261110a).
- 2026-11-09: Home "Recent results" showed "Result not recorded" with no scores for games whose published scorecard had the scores (e.g. Heartlake vs Imran XI, 6 Sep). The home strip reads `/api/public/fixtures-page`, which never applied the upload backfill that the live page uses. `_public_fixtures_page_payload` now calls `_fill_results_from_uploaded_scorecards` too (`main.py`), so the result, scores and scorecard link match "Latest scorecards".
- 2026-11-09: One score format for every page: all out is now "runs/wickets" (e.g. "154/10"), the same text in Home, fixtures, the live page and the published scorecard (`_side_score_text` and `_scorecard_from_archive` in `main.py`; `inningsBlock` in `scorecard.js`; `renderPublishedScorecard` and the ball-by-ball header in `public_match.js`). Innings with batting or bowling data are open by default on both pages; an innings with no data stays closed unless no innings has data. Asset versions bumped: `public_match.js` v20261110b, `scorecard.js` v20261110b. The Python change needs an app restart to show on the API output. The Match ID chips under the live scorecard (`matchIds` in `public_match.js`) now read the published innings' score (I1 "215/9") instead of "missing" when there is no ball-by-ball scorebook; `public_match.js` is v20261110e.
- 2026-11-09: Live match page and its linked published scorecard now show the same Match ID (e.g. `M-FA879005`, from the card id, the same code `/scorecards/a-…` uses). The fixture payload sends `published_match_code` (`_public_match_payload` in `main.py`), and `matchIds` in `public_match.js` uses it, so the innings IDs (`M-FA879005-I1`) match too. An innings with no score shows "–" on both pages. Needs an app restart to take effect.
- 2026-11-05: Scorecard preview can now delete a duplicate upload. When a "Possible duplicate" is the same photo (same file hash/fingerprint, or same file name saved as .jpg/.png/.HEIC) or the same innings (same batting team and total or mostly the same batters), the preview shows "Delete duplicate <code>" and `POST /api/scorecards/{id}/remove-duplicate/{other_id}` removes the other upload, its unshared file, and the matching flags (admins only; published copies need confirmation; the other team's innings is refused with a hint to Join). The preview response gains `duplicate_candidates`; those ids are no longer offered as "Link" candidates (`main.py`, `scorecard.js`).
- 2026-11-05: Fixed a player's match counts not tallying between "Year wise" (8) and "Club wise" (9) on the player stats page. When a card is for two clubs, a batter's dismissal note ("bowler: Amit S" / "fielder: X") credited a match and a wicket/catch to that bowler or fielder under the batter's club, even though he played for the other club in that game. `build_player_pending_stats` now skips a named bowler or fielder who played for the other side (`cricket_store.py`); stats refresh version bumped to `two-club-archive-owner-2` so stored stats rebuild. Amit S now shows 1 + 2 + 5 = 8 matches club-wise, same as year-wise.
- 2026-11-05: Stats page (Team roster, Team played scoreboard, rankings) showed all zeros for a club whose numbers are in an earlier season (e.g. Amit CC, 2024 only) because the page always opened on the current season. The Stats page now asks the dashboard for `selected_season_year=auto`: the current season, or the club's latest season that has matches when the current one is empty (`build_dashboard` in `cricket_store.py`, `app.js`). Picking a season in the dropdown still works as before.
- 2026-11-05: Home hero greeting ("Good morning, Name") now stays on one line and uses a smaller font than the "Season · Club" label (`dashboard_home.css`, `styles.css`).
- 2026-11-05: Fixed Amit CC (and any club that first appears from an uploaded scorecard) showing 0 members and missing from the player's login clubs. Cause: an older plain team row with the same name and no club made `_write_relational_state` save memberships without a club, so the club link vanished on reload. A club-linked membership now gives that team row its club (`cricket_store.py`). Also fixed the home-page error "match.availability is undefined" for a club with no fixtures (the dashboard sends `{}` for "no upcoming match"; `renderDashboard` now treats it as none, and the WhatsApp text and schedule list tolerate missing availability).
- 2026-11-05: Home hero tidied into a clean two-line header: small label "Season 2026 · Club name" and one title "Good morning/afternoon/evening, Name" (local time). The extra "Welcome back" line was removed (`index.html`, `app.js`, `dashboard_home.js`).
- 2026-11-05: Home page now shows a single greeting: the hardcoded "Good evening" line above "Season 2026" was removed; the time-based "Good morning/afternoon/evening, Name 👋" remains (`index.html`, `app.js`, `dashboard_home.js`).
- 2026-11-05: The home hero's small "Good evening" line was hardcoded and clashed with the time-based greeting; it now follows local time too (`app.js`, `renderDashboard` hero eyebrow).
- 2026-11-05: Home page greeting now follows the local time ("Good morning/afternoon/evening, Name") instead of "Welcome back". Fixed the home-page error "can't access property venue, match.details is undefined" for fixtures without details (`renderSelectedMatch` / `renderFormValues` in `app.js` default `details` and `scorecard`).
- 2026-11-04: Fixed a published two-club scorecard (e.g. Heartlake CC vs Amit CC) showing 0 players / 0 stats for the visiting club: `archive_belongs_to_club` now also honours the club names stored on the upload (`archives.club_names`), so the card counts for both clubs and `member_club_stats` / `club_summary_stats` are built for the second club. Checked on a copy of local data: Amit CC went from 0 to 14 player rows (e.g. Sarbajeet 66, Soorav 36, Vishnu 28).
- 2026-11-04: Wording clean-up: removed the "Mode" card and "Public read-only mode" / "Read-only" labels on Fixtures, and scorecard upload progress now says "Reading the scorecard" instead of naming Google Gemini/Ollama (`/api/scorecards/reader-info` label is "scorecard reader"). The privacy page still names Google Gemini as a data processor.
- 2026-11-04: Admin Center: the superadmin now sees every club's scorecards waiting for review (grouped by club) whichever club is selected; the club selector only picks the roster and club controls. Matches `/api/admin/review-queue`. Checked on local data: 42 scorecards and 8 clubs on every club selection.
- 2026-11-04: Local review fixes. (1) A scorecard that is read but still waiting for admin approval now registers its two clubs (e.g. "AMIT CC" from the 2024 Amit CC vs Heartlake card, which sat in "Needs admin review"); players and memberships are still only created from approved cards (`_published_scorecard_matches`, `_register_played_fixture_teams`). (2) Players who only have a typed club name (e.g. "Amit CC") are linked to the registered club (`_repair_typed_club_links`). (3) Stats: yearly totals now equal overall totals (they were scoped to the selected club); club-wise figures use the team each player played for - taken from the player rows' `Team:` tags, else from the innings team names, else inferred from the card's two clubs and its "won by N runs/wickets" result (`_archive_for_club_side`, `_infer_innings_teams`), so a match is no longer counted for both clubs. Verified on a copy of local data: total = yearly = club-wise runs for every player except 3 players' wickets from fixture rows (Amit G, Ravi, Prem). Online fixtures and uploaded scorecards both feed `member_summary_stats`, `member_year_stats` and `member_club_stats`. Known: `test_u02` / `test_u03` still expect the old "Heartlake + Coca Cola only" `visible_clubs`; the picker uses `my_clubs` now.
- 2026-11-04: Fixed Azure internal server error (`file is not a database`): rebuilt the corrupted production SQLite file and switched SQLite to the rollback journal on Azure (WAL stays on locally). Details in "Azure data architecture".
- 2026-11-02: Added superadmin Admin Center controls to disable and re-enable clubs without deleting their match history. Disabled clubs are hidden from regular club choices and blocked for members; superadmins can restore them. Documented the user's request in Prompt And Requirement Log.
- 2026-11-02: Restarted the local app on port 8090 and deployed the current ZIP package to the Canada Central Azure App Service. Azure reported `RuntimeSuccessful`; production `/api/health` returned HTTP 200. The full local QA suite was interrupted during external AI checks and did not complete.
- 2026-11-02: Reorganized Admin Center into a section menu with a dedicated Club Maintenance panel and separate Overview, Unique Visitors, Scorecard Tools, Archives, Audit Log, and Fixtures panels. Added keyboard navigation and mobile-friendly menu scrolling.
- 2026-11-02: Limited the signed-in Clubs page for superadmins to their current club. The full club directory remains available in Admin Center; refreshed the Clubs page script cache key.
- 2026-11-02: Restored Disable club and Re-enable club controls in the client-rendered Club Maintenance card, which replaces the initial server-rendered details after loading. The card now shows active/disabled status and retains permanent deletion.
- 2026-11-02: Fixed the Unique visitors Internal Server Error on Windows by adding the missing IANA time-zone database dependency; `America/Toronto` hourly and date grouping now resolves through `tzdata`.
- 2026-11-02: Scoped Scorecards to the signed-in user's current club by default, included shared scorecards for either playing club, and restricted changing the club filter or viewing All clubs to superadmins. The API enforces the same scope; the superadmin selector lists registered clubs even without scorecards.
- 2026-11-02: Allowed players from either participating club to enter live match scores. Restricted saved-ball corrections, undo, scorecard edits, lineup changes after initial setup, and historical edit mode to participating-club captains, club admins, and superadmins; opponent-club players can find the shared match in Quick Score.
- 2026-11-02: Fixed club player stats leaking across teams: Home selected-year rankings, Stats summaries and season trends, highest scores, milestones, and focused-club snapshot leaders now use club-filtered scorebook performance. Stale materialized top-batter rows can no longer override the live selected-club rankings. Afghan Eagles' figures no longer appear as Heartlake stats unless they actually played on Heartlake's side. See "Club-specific player stats".
- 2026-11-02: Afghan Eagles club stats now include Shahid and other recorded players' batting/bowling figures from their innings in a Heartlake-owned fixture, without moving the fixture out of Heartlake. See "Club-specific player stats".
- 2026-11-02: Afghan Eagles Home and Matches now include its recorded Heartlake-opponent fixture in Afghan perspective; signed-in Rankings uses only players linked to the focused club, and played-match data feeds the snapshot and player summaries.
- 2026-11-02: My availability now includes a player's recorded appearance in a match owned by the opponent club, uses scorebook team-side attribution, and presents the past fixture as read-only.

- 2026-11-02: Fixed the remaining Afghan Eagles roster bleed: unmapped primary teams no longer inherit Heartlake as their club, and unrelated team affiliations block fallback to a user-selected club.
- 2026-11-02: Replaced long hashed Player IDs with persisted four-digit numeric IDs (`1000` for the superadmin; other IDs increment from `1001`) and migrated existing IDs.
- 2026-11-05: Admin Center now follows the delete rule too: the server-rendered page and the script-rendered Club Maintenance card show "This club cannot be deleted: it still has N player(s), N match(es), N scorecard(s)…" with the delete form removed when the club has any, and show the delete form only for an empty club. New `GET /api/admin/clubs/{id}/delete-check` (superadmin) returns `can_delete`, the counts and a reason; `DELETE`/form delete still refuse with 409. Verified on the running app: all 8 clubs report can_delete=false with counts, DELETE returns 409, and the Coca Cola XI / Vinny XI pages show the note.
- 2026-11-05: Rolled back the "delete a club but keep multi-club players' other data" change. A club now can only be deleted when it has no players, no matches (own fixtures or as opponent) and no scorecards; otherwise `DELETE /api/admin/clubs/{id}` and the Admin Center form refuse with a message saying what is still in it and suggesting Disable. Verified on a DB copy: all 8 clubs refused with their counts, an empty club deleted.
- 2026-11-05: Clubs page Club Wise stats now list the same clubs as the club picker (`my_clubs`) plus any club with real stats, so a stale or disabled membership with no games no longer shows as an extra row of zeros.
- 2026-11-05: Linking two clubs' separate innings uploads now keeps both Match IDs working: the absorbed upload's id is stored in `joined_upload_ids` on the joined scorecard, so either club's Match ID and `/scorecards/{id}` link opens the one match. The joined card stays published if either half was published. Verified on a DB copy that joining leaves one card with both innings and unchanged player and club run totals.
- 2026-11-05: Club links now follow the side a player played for. A club a player only played against (e.g. TP Community for a Coca Cola XI player) is removed from their club and team memberships, unless it is their primary club or a club they typed on their profile. Every club played for in any game stays visible. Cards with swapped innings labels are detected from players' known teams. Applies to all players.
- 2026-11-05: Database backups: verified automatic copies at start-up and every 6 hours, 48 recent + 30 daily kept, optional off-site copy to Azure Blob (`CRICKETCLUBAPP_BACKUP_BLOB_SAS`), start-up health check that alerts site admins, superadmin page `/admin/backups` (back up now, download). Club registration from played games no longer runs in a background thread (it could save over a newer change). See "Database backups". Each copy is switched to the rollback journal (no -wal/-shm side files), so restoring one on Azure Files never brings WAL back.
- 2026-11-05: Fixed players of a club named differently on the card ("Amit 11" for Amit CC) being added to the uploader's club (Heartlake) when the card is approved. `_published_scorecard_matches` now maps each innings' batting/bowling team to the same registered club as the card's teams, so on approval Amit CC gets its 9 batters, Heartlake keeps its bowlers, and Amit sees Amit CC in his clubs. Verified on a copy of local data (Amit CC 0 -> 9 players; Dixit/Vishnu/Sarbajeet only in Amit CC; Sam/Checkley only in Heartlake). A card waiting for review still registers clubs only (players come with approval).
- 2026-11-05: The AI reader no longer applies a learned name fix when the corrected name is already another player on the same card ("Ravi" -> "Rams" while Rams also bowled merged two bowlers). The name is kept and the preview says why (`ai_vision._apply_learning`).
- 2026-11-05: Fixed the 2nd innings photo turning into a second scorecard (a second Match ID) after a reload. The 2nd photo's file name/hash and joined-half ids were not saved in the database (`archives.extra_json`), so after a restart the upload-folder scan found the 2nd photo unclaimed and made a new "Ready for review" upload. `ARCHIVE_EXTRA_KEYS` now keeps `second_photo_*`, `second_uploaded_by` and `joined_upload_id(s)`, and `sync_uploads_in_store` skips any file that is a scorecard's 2nd photo (`cricket_store.py`). Verified: upload + 2nd photo + restart + folder scan = 1 scorecard (the old code made 2).
- 2026-11-05: When the AI reader gives both innings of a 2-innings match the same batting and bowling team ("Scarborough Pro" batting twice against Heartlake), the preview now asks the checker to set the right team from each photo's "Innings of" line (`_repeated_batting_side_note`). No automatic swap: on the 27 Jul 2025 card the page that looked like the 2nd innings was really Heartlake's, so a guess would have been wrong.
- 2026-11-05: Adding a 2nd innings photo that the old bug had already turned into its own unread "Ready for review" card (same photo, never read or reviewed) no longer fails with "This photo was already uploaded": that stray card is removed and its photo becomes this scorecard's 2nd photo (`_is_unread_folder_copy`, second-photo endpoint). Verified on a copy of local data: 37 -> 36 uploads, M-0825ED4D gets both innings.
- 2026-11-05: AI reader prompt: the batting team is the team after "INNINGS OF" on that page (even if it is the 2nd team in PLAYED BETWEEN), "(2nd)" there means innings 2 (`ai_vision.PROMPT`). The 27 Jul 2025 Heartlake page was read once as Heartlake and once as Scarborough Pro batting.
- 2026-11-05: "🤖 Read again with AI" now reads the 2nd innings photo too and joins it, instead of re-reading only the 1st photo and dropping the other team's innings (`/api/scorecards/{id}/ai-read`). When the 1st photo is written as the 2nd innings ("HEARTLAKE (2nd)"), the other photo's innings goes first (`_join_innings_photos`). Verified on a copy of local data: M-CA36A6F1 = Scarborough Pro 298/9 (I1) + Heartlake 160/9 (I2).
- 2026-11-05: A 2-innings uploaded scorecard with no result written now shows the result worked out from the two totals ("Imran XI won by 94 runs", "X won by 4 wickets", "Match tied") instead of a score like "Imran XI 219/8" (`_result_from_innings` in `_scorecard_from_archive`). A result written on the card is never replaced.
- 2026-11-05: Home "Recent results" / live page: a fixture with no result takes the result and scores from the published scorecard of the same game (same date, same two teams), and gets `scorecard_url` (`_fill_results_from_uploaded_scorecards` in `_public_live_page_payload`).
- 2026-11-05: Scorecards list: an upload whose date wasn't read is grouped under "Date not set - add it with ✏️ Edit scorecard" with "?" in the date box, instead of "January 0" / "MON undefined JAN" (`scorecards.js`).
- 2026-11-06: AI reader copies the ball-by-ball marks and the app does the counting. The prompt now asks for each batter's scribbles as `ball_by_ball` ("1 . 4 . 2 6 W") and each bowler's analysis boxes as `over_marks` (one string per over: ".", 1-6, "W", "wd", "nb4", "b1"/"lb1"). `ai_vision._fill_from_marks` (first step of `_apply_learning`) counts them exactly: batters' balls faced, 4s, 6s, dots, 1s, 2s, 3s; bowlers' overs, maidens, runs, dots, wides, no balls, 4s and 6s conceded. Numbers written on the card always win; only empty ones are filled, and a difference becomes a "Check ..." note. The scorecard page shows the split under each name ("Dots 1 · 1s 2 · 2s 2 · 3s 0"; "Dots 4 · Wd 1 · Nb 0 · 4s 1 · 6s 1"). Verified with a stand-in reading: Dixit 10 (6 balls, 1 four), Amit S 7* (4 balls, 1 six), Keshu 1.5-0-18-1. Cards read before this change keep their "–" until they are read again with AI.
- 2026-11-06: Ball-by-ball counting, after the first real read (Scarborough Pro vs Heartlake): when no batter in an innings has a dot in the ball-by-ball (the scorer wrote only scoring shots), balls faced and dots are not counted from it (that gave "Ali 107 off 28"); 4s, 6s, 1s-3s still are, and the preview says balls must be typed in. A TOTAL filled from the marks is flagged. Prompt: "not" in HOW OUT + "out" in BOWLER = not out (Roy / King were read as retired out); bowlers' overs = used boxes even when the marks can't be copied (the Heartlake page came back with no overs).
- 2026-11-06: Ollama backup when Gemini's free limit is used up: requests now send `"think": false`, `num_ctx` 32768 and `num_predict` 8192 (`OLLAMA_NUM_CTX` / `OLLAMA_NUM_PREDICT` in .env) - the old 8192 context was too small for the prompt + photo + a full card. A JSON answer left inside a thinking model's thoughts is still used. When the backup fails, the message now says why ("The local AI (Ollama qwen3-vl:4b) was tried too: ...") instead of only "Today's free AI limit is used up". Non-thinking vision models are preferred (`qwen2.5vl:7b` first). Checked on Dhruvika's PC: `qwen3-vl:4b` (a "thinking" build) ignores `think: false`, spent 39 s on a 50-token reply and returned only thoughts - use `ollama pull qwen2.5vl:7b` for the backup. Then Ollama crashed ("connection forcibly closed" = out of memory) with the 32768 context and a full-size photo: defaults are now `num_ctx` 16384, `num_predict` 6144 and a 1400 px photo (`OLLAMA_IMAGE_EDGE`), and that crash is explained in plain words. On a laptop the smaller `qwen2.5vl:3b` is the safest backup model.
- 2026-11-06: Upload page: the two photo boxes are "1st innings photo (the team that batted first)" and "2nd innings photo (the team that batted second)"; either one alone, or both, can be uploaded. A photo given only in the 2nd innings box is uploaded with `innings_number=2` (`POST /api/scorecards/upload`, `_mark_single_innings_number`), so the card shows I1 missing / I2 recorded, and the preview button says "Add the 1st innings photo"; the added page goes in as innings 1. Verified with a stand-in reading: 2nd only -> I1 missing, I2 recorded; 1st added -> both recorded, "Coca Cola XI won by 7 wickets" (`scorecard_upload.html/.js`, `scorecard.js`).
- 2026-11-06: AI training: new worked example `app/ai_examples/example_4` - the Heartlake page of Scarborough Pro vs Heartlake (27 Jul 2025), written out from the photo with every batter's ball-by-ball marks, TOTALs (136 + extras 24 = 160/9), dismissals (not / out = not out), bowlers' overs from the boxes and wickets from the BOWLER column, plus six lessons. It is sent first with every read; `AI_WORKED_EXAMPLES` default is now 4 (examples 4, 1, 2, 3). The older examples had no `ball_by_ball`, so the reader copied them and left those fields empty. Uncertain rows are marked `unsure`; the Scarborough Pro page was not used (several TOTALs and How out rows can't be read with certainty, and a wrong example teaches mistakes). Ball-by-ball: dots count as written only when they are at least 15% of an innings' marks (3 stray dots in ~120 runs-only marks no longer turn into "balls faced").
- 2026-11-07: Fixed every new upload being refused as "the same photo as 'image.jpg'". The photo fingerprint was an 8x8 average hash (64 bits) and all green-lined scorebook pages looked alike (different pages 7-8 bits apart, limit 5). It is now a 32x32 difference hash (`d32:` + 256 hex, `scorecard_checks.image_fingerprint`): on real photos the same photo re-saved like WhatsApp is <= ~20 of 1024 bits apart, two different pages >= ~340. Old fingerprints are never compared with new ones; an older upload gets its new fingerprint from its photo the first time it's compared (upload check and Admin Center "Scorecard checks"). Exact copies are still refused by the file hash. Tested on the live DB copy (DB-Backup, Nov 7): two different pages upload, the same page re-saved is refused.
- 2026-11-07: Club-wise player stats now always add up to the player's total and to year-wise: each of a player's matches is counted for exactly one of his clubs - the side he played for on the card (or the fixture's club / opponent club, else the uploading club, else his primary club), using the same per-match counting as the total (`_member_club_rows_one_club_per_match`). On the live DB copy 79 of 225 players were off (Amit S: 13 matches by year, 15 by club); now 0 (Amit S: Heartlake 10 + Coca Cola 2 + Amit CC 1 = 13).
- 2026-11-07: Side detection on uploaded cards: a card's own team tags no longer vote on that card, each player votes once, players tagged with both teams don't vote, and it takes 3+ players and twice the evidence to override the innings labels (`card_sides_are_swapped`, `_anchors_without`); team tags on the upload are only used when the innings don't name the club. Heartlake vs Coca Cola (12 Jul 2026) had Heartlake's batters (John, Amit S, Checkley) counted for Coca Cola.
- 2026-11-07: Club win rate / standings: who won is read from the result ("X won by ...", "X lost") matched to the two teams, else from the two innings totals (`club_match_record`, `_archive_outcome`, `_fixture_outcome`). A result saying "won" without naming the club no longer counts as a win for everyone, a card is only counted for clubs that played in it, and the win rate is wins out of matches with a known result (`matches_decided`; a one-innings card has none). Rankings "Club standings" shows Lost too. Live DB copy: Heartlake W3 L4 (was W3 L0), Coca Cola XI W2 L1 (was W3 L0).
- 2026-11-07: A scorecard now shows under every club on it: the clubs saved on the upload (both teams) are kept when the store loads instead of being replaced by the uploader's club, so a one-innings card (e.g. Heartlake 154 vs Imran XI, 26 Jul 2026) is listed in Imran XI's scorecards too.
- 2026-11-07: Runs per over: the AI reader copies the runs written under each bowling box into `over_runs` ("5-0 7 11 6 14 6 9"), or the app counts them from the box marks. When the card doesn't give them, a bowler's overs, runs and maidens come from `over_runs`; a written figure that differs by more than 2 becomes a "Check ..." note. The scorecard page shows "Runs per over: 5 · 7 · 11 ..." under each bowler (`ai_vision._fill_from_marks`, `scorecard.js`). Verified with a stand-in reading: Sam [5, 7] -> 2-0-12-1, economy 6.00.
- 2026-11-07: Balls faced / 4s / 6s: the reader copies the BALLS RCD, 4's and 6's columns when the scorer filled them in; they win over the counted marks. With no dots and no BALLS RCD the photo doesn't hold balls faced - they stay empty with a note (a guess would give wrong strike rates).
- 2026-11-07: Match date: checked on the live DB copy - all 18 AI-read cards took the date from the scorecard. An unread card no longer gets its upload time as the match date: a photo's date is used only when the camera wrote it into the photo, never the file's saved time (`_photo_metadata_date`; WhatsApp / iPhone sharing removes the camera date). The 4 undated live cards (5ed8f26c, 5d206d48, 72b12351, cd3b9dde) are 2nd-innings photos the old "two Match IDs" bug turned into cards of their own.
- 2026-11-09: Player profile, read only: scorecard names of registered players link to `/players/<player id>` (`player_public.html/.js`, `GET /api/public/players/{player_id}`): name, clubs, "also written as", career / season-by-season / by-club stats and recent matches with his batting and bowling. No phone, email or age. A name is linked only when it clearly is one player (the club on that side first, then everyone).
- 2026-11-09: ✏️ Edit scorecard: changing a player's name (batter, bowler, or the bowler in How out) changes the same name everywhere on the card, both innings, with a message "'Keshu' was also changed to 'Keshav K' in 3 other places" (`scorecard.js` `wireRenameEverywhere`). Tested in a browser on the live DB copy.
- 2026-11-09: AI names mapped to the club's players: after each read, batters are matched to the players of the batting club and bowlers / fielders to the bowling club (`_map_card_names_to_rosters`): an exact name or alias becomes the registered name (CHUCKLEY -> Checkley), a clear one-letter-ish misspelling of exactly one player is corrected with a "Check" note, a bare first name two players share ("Amit": Amit S and Amit G) stays as written, and a How out bowler written differently from the bowling list ("Nandeep" / "Nandip", "Haris" / "Harris") uses the bowling-list name so his wickets count.
- 2026-11-09: What the AI is told about players ("RAG"): besides the club's roster, corrections and names on its past cards (now every published card the club played in, not only its own uploads), the reader gets each player's other spellings ("Checkley (also written Chuckley)"; a first name two players share is never given) and the players of the clubs it plays most (`_ai_aliases`, `_ai_other_clubs`, `ai_vision._prompt`). It is built from the live database at every read, so it learns from every card Amit approves.
- 2026-11-09: "Are these you?" on the signed-in player's profile: names on scorecards that look like him (near spelling "Checkly", same sounds "Chukli", initials "CJ", first name only) with the matches they appear in; "This is me" adds the name to his aliases and folds an unclaimed duplicate player record of that name into his, so those matches count in his stats; "Not me" hides it (`GET /api/player/name-suggestions`, `POST /api/player/name-suggestions/claim`). A name that is another registered player, or could be (a first name another player also has), is never suggested and can't be claimed. Tested on the live DB copy: matching tightened after "Harry" was suggested to Barry.
- 2026-11-09: Captains and man of the match: the reader copies the CAPTS. HOME / VISIT and MAN OF MATCH boxes (`match.captains`, `match.man_of_match`); the scorecard's Match details show them.
- 2026-11-09: Training: second worked example `ai_examples/example_5` (Amit CC page of Heartlake vs Amit CC, 16 Jun 2024, live card aefcc3e5) with ball-by-ball, runs per over under each box (Sam 5 7 11 6 14 6 9) and both captains; examples are sent in the order 4, 5, 3 (printed card), 1. Live photos are on Azure only, so more examples need the photos (or `python scripts\add_ai_example.py <id>` on a copy that has them).
- 2026-11-09: Team short code: "Imran XI" showed as "IX"; a trailing XI / 11 is no longer the code (Imran XI -> IMR, Coca Cola XI -> CCXI).
- 2026-11-09: Saved player stats are rebuilt once after this update (`STATS_REFRESH_VERSION` "one-club-per-match-3"), so club-wise stats use the new one-club-per-match counting. A nearly blank picture's fingerprint is never "the same photo".
- 2026-11-07: Captains and man of the match: the reader copies CAPTS. HOME / VISIT (or "(c)") into `match.captains` and MAN OF MATCH into `match.man_of_match`; the scorecard page shows "Captains" and "Man of the match" in Match details (`_card_people`).
- 2026-11-07: Read-only player profiles: every registered player's name on a scorecard links to `/players/<player id>` (`player_public.html/.js`, `GET /api/public/players/{key}`): clubs, aliases, career, season-by-season and club-by-club stats (the same numbers as the stats pages) and recent matches with his runs and bowling. No phone, email or age. A name is linked only when exactly one registered player fits - first among the players of the club on that side (`_member_for_card_name`, `_link_card_players`). Checked on the live DB copy: Amit S (1000) 13 matches, Heartlake 10 + Coca Cola 2 + Amit CC 1, 13 recent matches.
- 2026-11-07: Names read by the AI are matched to the registered players of the club on that side (batters to the batting club, bowlers and fielders to the bowling club): an exact name or alias becomes the registered name, a clear misspelling of exactly one player of that club (same first letter, length within 2, 85%+ similar and clearly better than the next) is corrected with a "Check it" note; anything unclear is left as written (`_map_card_names_to_rosters`, run in `_apply_ai_template`). Live DB copy: Checkly -> Checkley, Jon -> John, Keshuu -> Keshu (Imran XI).
- 2026-11-07: ✏️ Edit scorecard: changing a player's name changes the same name everywhere on the card (batting, bowling and the bowler in How out, both innings) and says how many places changed (`wireRenameEverywhere`).
- 2026-11-07: "Are these you?" on the player profile: names on scorecards (his clubs' side only) that look like the signed-in player - spelling (Checkly, Chuckly), short forms (Chuck, Chukli), first name only (Amit), initials (CJ for a two-word name) - with the scorecards they are on. "This is me" adds the name to his aliases and merges an unclaimed duplicate player record of that name into his; "Not me" hides it. A name of another registered (signed-up) player is never offered, and "Amit G" is not offered to "Amit S" (`GET /api/player/name-suggestions`, `POST /api/player/name-suggestions/claim`).
- 2026-11-07: Team codes: a trailing XI / 11 is no longer the code ("Imran XI" showed as "IX", now "IMR"; "Coca Cola XI" "CCXI") (`shortCode` in `scorecard.js`, `public_match.js`).
- 2026-11-07: AI training from the live data: only approved cards whose numbers fully add up are fit to teach (4 of 17 on the live DB copy; "approved" cards still had wrong digits, e.g. the 16 Jun 2024 card's 3rd bowler saved as "Rams" when the card says RAVI). New worked example `app/ai_examples/example_5` - the Amit CC page of Heartlake vs Amit CC (16 Jun 2024), written out from the photo with runs per over under every bowling box (Sam 5, 7, 11, 6, 14, 6, 9 = 58), captains, "AMIT 11" = AMIT CC, run out with the fielder in the BOWLER column. Examples sent with every read: 4, 5, 1, 2. The other clean live cards (d09723de, 658bf977, 3e941d63) need their photos from the Azure uploads folder to become examples.
- 2026-11-02: Added `scripts/restart_local_app.ps1` to safely stop the app on port 8090, relaunch it hidden, and wait for `/api/health`; documented manual use.
- 2026-11-02: Changed generated Player IDs to globally neutral `P-` IDs with 128 hash bits, migrated legacy `CCP-` IDs, assigned IDs as played-game players enter the directory, and surfaced those IDs in registration's Not linked yet list.
- 2026-11-02: Prevented account-selected clubs from overwriting explicit player-club memberships; kept club rosters club-specific and removed global players from focused club scorebook selectors, so Afghan Eagles players and stats do not appear under Heartlake without Heartlake membership or match records.
- 2026-11-02: Added superadmin unique-visitor analytics with hourly/daily/monthly/yearly reports and peak hour; stable Player IDs for accounts and profiles with name/alias linking; optional date of birth at registration and on the player profile; and a live scorecard viewer count. Updated the manual ZIP deployment instructions.
- 2026-11-01: Prepared `scripts/deploy_azure.sh` for this repository and Windows Git Bash: stage `MD/README.md` and `MD/READMELLM.md` under the expected names, use `cp` / Python ZIP fallbacks when `rsync` / `zip` are unavailable, and support an explicit `PYTHON_BIN`. Verified the local app health endpoint and `/score` before deployment.
- 2026-11-01: Deployed `main` (`7b8238b`) to `cricketcanclubs-web` in Canada Central with `scripts/deploy_azure.sh`. Azure reported `RuntimeSuccessful`; `/api/health`, `/api/scorecards/reader`, and `/score` returned HTTP 200. Confirmed the Gemini setting remains a Key Vault reference, and the ZIP had no runtime data, uploads, duplicates, database files, or `.env` entries.
- 2026-11-01: Completed retired-out scoring and return changes: record RO without runs, a legal ball, bowler credit, or a team wicket; show temporary retired status until the batter returns; clear it and resume their figures on return; persist incoming batters; and keep returned batters scoreable. Added migration and regression coverage. The initial return-picker release was deployed to Azure with the Gemini Key Vault reference intact and runtime data/secrets excluded.
- 2026-11-01: Fixed innings completion and scorecard presentation for retired-out returns. Exclude temporary retirements from team wicket totals and all-out status, while preserving the retirement event to support replacement and later return. Added regression coverage for two retired-out batters returning and scoring; updated return labels and Azure deployment notes.
- 2026-11-01: Deployed the retired-out return option to the Canada Central Azure App Service. Production returned HTTP 200, the scorecard reader reported Gemini, and Quick Score served the cache-busted bundle with the return picker. Confirmed the Gemini Key Vault reference remained configured; the package excluded runtime data and secrets.
- 2026-11-01: Let a retired-out batter return in the same innings from the next-batter picker, continuing their existing batting figures and status.
- 2026-11-02: Deployed the latest retired-out scoring and display changes to the Canada Central Azure App Service. Production health returned `ok`, the scorecard reader reported Gemini, and the refreshed Quick Score/public scorecard assets served the retired-out changes. Confirmed the Gemini app setting remains a Key Vault reference; the data-free package excluded production runtime data and secrets.
- 2026-11-01: Changed retired-out presentation and alerts to `RO` / "Retired out" against the dismissed batter, and excluded even legacy retired-out records from bowler figures.
- 2026-11-01: Added Retired out to live and authorized past-match scoring as a temporary batter departure with no runs, ball faced, legal delivery, team wicket, or bowler attribution; fixed next-batter selection and added scorebook regression coverage.
- 2026-11-01: Clarified retired out as a temporary departure, not a wicket. Persist it with no wicket flag, and exclude it from team wicket totals, fall-of-wickets, over wicket counts, all-out calculations, and wicket celebrations; retained a distinct retirement alert and return flow.
- 2026-11-01: Applied the no-wicket rule to the legacy delivery assistant and AI Live Scorer, including retired-out interpretation, projected score, and batter replacement. Added an AI scorer regression.
- 2026-11-01: Clear a returning batter's retired-out tag on the public scorecard when they reappear in the batting pair, with or without an explicit incoming-batter marker.
- 2026-11-01: Added a direct PDF download to public match scorecards. The PDF includes full innings batting/bowling tables, extras, totals, did-not-bat players, and fall of wickets; added a ReportLab dependency and PDF regression coverage.
- 2026-11-01: Fixed role-based deletion for incomplete fixtures and scorecard uploads, protected completed match records, archived past scored fixtures with season/date filtering, and persisted Available for members confirmed in a past scorebook. Updated the read-only historical availability view and added regression coverage.
- 2026-11-01: Registered missing clubs and scorebook players from played fixtures in the player-registration options, preserving existing memberships and ignoring unscored fixtures; added idempotency and team-attribution regression coverage.
- 2026-11-01: Added authorized incomplete-match deletion to Quick Score and public live scorecards, including started scorebooks; retained the completed-match safeguard and linked successful deletion to start another match.
- 2026-11-01: Deployed the retired-out clarification and returning-batter scorecard fix to `cricketcanclubs-web` in Canada Central. Production health returned `ok`, the scorecard reader reported Gemini, all updated assets returned HTTP 200, and `GEMINI_API_KEY` remained a Key Vault reference. The verified ZIP excluded runtime data, uploads, caches, and secrets.
- 2026-11-01: Kept authorized edit mode in the active live-scoring flow until both innings complete, added the second-innings transition and Wide/Wide +1..+4 choices, and enabled run-outs on wides and no-balls with scorebook regression coverage.
- 2026-11-01: Enabled authorized live-style ball-by-ball scoring in past-match edit mode, including append persistence, recalculated innings/result state, notification suppression, refreshed assets, and RBAC regression coverage.
- 2026-11-01: Added RBAC-gated, live-style Quick Score correction mode for fixing or removing any saved past-match delivery in either innings, with refreshed editor asset versions and Home/match-center links.
- 2026-11-02: Included scored/started past fixtures in Recent results despite stale Scheduled/TBD metadata and added a club-scoped, RBAC-gated Home edit link.
- 2026-11-01: Kept played 2026 fixtures visible when their scorebook is still in progress; enabled authorized post-match scorecard-summary corrections and added club-scoped, incomplete-only fixture deletion for captains, club admins, and superadmins.
- 2026-11-01: Deployed the latest live-style past-match scoring code to the Canada Central Azure App Service. The data-free zip deployment and site restart succeeded; production health returned `ok`, the scorecard reader reported Gemini, and Quick Score served the updated assets with wide variants and run-out support. Production app settings and persistent runtime data were not included in or changed by the deployment.
- 2026-11-02: Two-photo scorecards: a card photographed on two pages can be uploaded as two photos. Upload a scorecard has an optional "2nd innings photo"; and when an upload has only one innings, its check page shows "📷 Add the 2nd innings photo" (uploader, the club's scorers, site admins; until it has both innings). The 2nd photo is read with the AI reader and the other team's innings is joined as innings 2 (match details missing from page 1, like the result, are taken from page 2); both photos show under "Original scorecard", and "Read again with AI" reads both. Same-photo and already-uploaded photos are refused. `POST /api/scorecards/{id}/second-photo`, `_join_innings_photos` in `app/main.py`; preview answers `innings_count` / `can_add_second_photo`; cards give `photo_urls`. Without AI reading the photo is kept and the 2nd innings is typed in with ✏️. `scorecard.js` / `scorecard_upload.js` / `scorecards.css` 20261102c.
- 2026-11-02: Scorecards menu: the date picker has no from / to limit (October 2026 games could not be picked), reacts on input, and moves Season to the picked date's year; Season always lists the current year. Home: fixed "clubKey is not defined" in `dashboard_home.js` (fromFixture ran before the club was known), which stopped Home's match lists. `scorecards.js` 20261102c, `dashboard_home.js` 20261102e.
- 2026-11-02: Innings uploaded separately are joined: when an upload has one innings and another upload (by any club) has the other innings of the same match - same date, the same two teams, the same venue when both name one, and a different batting side - the new photo is joined into the earlier upload as its 2nd innings photo (one scorecard, both photos, innings in the order written on the cards) and the check page says so. The same batting side twice stays a possible duplicate. Pairs uploaded before this change show "🔗 Join the two innings" on their check page. A published card stays published when the joined card passes the checks. `_find_other_half` / `_halves_match` / `_join_halves`, `POST /api/scorecards/{id}/join/{other_id}`, preview `other_half`. `scorecard.js` 20261102d.
- 2026-11-02: Edit names & teams: "✎ Edit names & teams" on the Score page (live and edit mode) fixes who batted first, a player's name everywhere in the match (or joins two spellings, e.g. Parvez / Parwez, line-ups too) and the bowler of a whole over; the result is worked out again. Captains / club admins of a playing club and superadmins only (`_require_match_score_editor`). `POST /api/matches/{id}/scorebook/edit` (actions `teams`, `rename`, `over_bowler`). `quick_score.js` 20261102i.
- 2026-11-02: Delete wrong scorecards: a finished match can now be deleted too ("Delete this wrong scorecard" on the Score page and the live scorecard, `DELETE /api/admin/clubs/{club}/fixtures/{id}?finished=1`, `can_delete_completed`), and a published uploaded scorecard ("✏️ Fix or delete this scorecard" on its page -> "Delete this scorecard", `DELETE /api/admin/archive/{id}?published=1`, preview `is_published`). Same roles as before (club captain, club admin, superadmin); both ask for a clear confirm and refuse without the flag. `public_match.js` 20261102i, `scorecard.js` 20261102e.
- 2026-11-02: Match ID: every scorecard has a Match ID (`M-` + 8 characters of its id, `_match_code`), shown on the scorecard, the check page and the Scorecards list; both innings of a joined match share it. Only innings with their batting written out count as innings (a page with one innings + the other team's total is ONE innings - `_usable_innings`), so the two pages of one match now join automatically. Possible duplicates list the Match ID and offer "🔗 Link with M-…"; the check page has "Other team already uploaded their innings? Enter their Match ID" (`POST /api/scorecards/{id}/link`), and the Upload page has an optional "Other team's Match ID" (`link_match_code`). Linking refuses the same batting side twice (a real duplicate) and unknown IDs. `scorecard.js` / `scorecards.js` / `scorecards.css` 20261102f, `scorecard_upload.js` 20261102e.
- 2026-11-03: Clubs from scorecards: a published uploaded scorecard now registers its teams as clubs, with their batters and bowlers as players, the same way scored fixtures already did (`_published_scorecard_matches` feeds `_register_played_fixture_teams`; run on publish / approve and on `GET /api/auth/options`). Example: Heartlake vs "AMIT CC" -> club "AMIT CC" with Amit S, Ali, Rishie, Sachin, ... selectable in registration. A team name that matches an existing club ("Coca Cola" -> "Coca Cola XI") uses that club; placeholder names ("Opponent", "Team 2") are skipped. Only published cards count, so a wrong AI reading doesn't create a club before someone checks it.
- 2026-11-03: Photos: the scorecard photo inputs (Upload page, "Add the 2nd innings photo", Admin Center upload) no longer force the camera (`capture` removed), so phones offer both "Take photo" and the photo library / files.
- 2026-11-03: Innings IDs: every match (Match ID `M-XXXXXXXX`, the parent) lists its innings as children `M-XXXXXXXX-I1`, `-I2` (a Test / multi-day match: `-I1` to `-I4`), each "recorded" (team + score) or "missing" (`innings_ids` on scorecards and list items, `_innings_ids` in `app/main.py`). The scorecard and check pages show them as chips with missing innings in amber, and the Scorecards list tags "⚠ Innings 2 missing" on uploaded cards. Linking accepts a Match ID or an innings ID (`M-XXXXXXXX-I2` links to its match). Check-list text now wraps on phones. `scorecard.js` / `scorecards.js` / `scorecards.css` / `scorecard_upload.js` 20261103a.
- 2026-11-03: Amit's two June 16 2024 pages (Heartlake 204/7 on one, Amit CC 207/7 on the other): they now join into one match in either upload order and, once published, register club "AMIT CC" with the players from both pages. Fixes: handwritten team names are matched loosely ("Hearthlake" / "Heartcake" = Heartlake, "AMIT 11" = "AMIT CC") and the joined card uses the registered club's name; the venue no longer blocks a join (the pages said "Dixie" and "Save Max" for the same ground) - date + both teams + a different batting side decide; the result written on only one page ("AMIT CC WON") is kept; the newest matching upload is preferred.
- 2026-11-03: Innings IDs follow the innings number written on the card: a page that says "Innings of Amit CC (2nd)" uploaded on its own shows `-I1` (the other team) as missing and `-I2` Amit CC as recorded, not the other way round (`written_inning_number` on archive innings).
- 2026-11-03: Matches scored on the Score page show the same Match ID and innings IDs on their live / public scorecard (`/live/{id}`, under the match details): `M-XXXXXXXX`, `-I1` / `-I2` (Test: `-I1` to `-I4`) with each innings' score, "to come" before it is played and "missing" on a finished match. `public_match.js` / `public_match.css` 20261103b.
- 2026-11-03: Admin Center review: each scorecard card shows its Match ID, and the "Reviewed extraction JSON" now carries `match.match_code` ("M-XXXXXXXX") and `innings[n].innings_id` ("M-XXXXXXXX-I1" ...), in both the server-rendered queue (`_json_with_match_ids`) and `admin_center.js` (`withMatchIds`, 20261103c). The IDs come from each record, so every earlier scorecard (uploaded, typed in or scored live) has them without re-reading. Saving the JSON with the IDs works as before.
- 2026-11-03: Finding linked matches: a published scorecard stays published when its other innings is joined (it used to drop back to "waiting for review" and vanish from Scorecards); and captains, club admins and superadmins now also see their club's matches still waiting for review in the Scorecards list, tagged "⏳ Waiting for review" and opening the check page (`pending` / `url` on list items). When both pages say "1st innings", the result decides the order ("won by N wickets" / a winner who passed the total chased; "won by N runs" batted first) (`_chasing_side`). `scorecards.js` 20261103d.
- 2026-11-03: Clubs you played for: clubs and players from played games (scored fixtures and published scorecards) are registered at start-up, after a publish / join, and in the background when the Clubs page opens (`_register_played_teams_in_background`, one run at a time); every player becomes a member of each club they played for, so those clubs show on "My clubs / switch club" (e.g. Ali: Heartlake + AMIT CC). Before, this only ran when the Registration page was opened.
- 2026-11-04: Player ID: the Player ID (and date of birth) are now read back from the `members` table - they were saved but never loaded, so every page said "Player ID: Pending" (Amit = 1000). Shown read-only on the profile and next to each name when picking a line-up (`roster_player_ids`, `quick_score.js` 20261104a).
- 2026-11-04: Club memberships: saving the profile no longer replaces a player's club links with the typed text (that is how Amit ended up with only "Amit CC"). Club links come from the games played (and club admins); a typed registered club name is added, nothing is removed (`_add_member_clubs_by_name`). Profiles broken by the old save are repaired on start-up / Clubs page (`_register_played_fixture_teams`). The profile field is now "Club memberships" and lists every club.
- 2026-11-04: Clubs page: everyone, the superadmin included, sees every club they belong to / played for (`my_clubs` in `/api/auth/me`; the page used to show the superadmin only the current club and search found nothing); a superadmin's search looks through every club. Server-rendered list too. `clubs.js` 20261104c.
- 2026-11-04: Stats in step everywhere: a club's stats count an uploaded scorecard only for the players who played FOR that club (Amit S's 24 for Amit CC was counted as a Heartlake innings) - `_archive_for_club_side` in `build_combined_player_stats`; a player's total and yearly figures count every club. Published scorecards are linked to the clubs of both teams. The Clubs page breakdown uses the player's own all-club rows first (2024 showed HS 24 with 0 matches) and shows no highest score without matches. Check on Amit (local data): total 64 = Heartlake 40 + AMIT CC 24 = 2026 33 + 2025 7 + 2024 24.
- 2026-11-04: Roles: fixed role IDs 1 superadmin, 2 club admin, 3 captain, 4 player (`ROLE_IDS`, `app_roles.role_id`, `role_id` in the user payload). Deleting a match or scorecard is now for club admins (of that club) and the superadmin only - captains manage and edit their games but no longer delete them.
- 2026-10-31: Refreshed `main` to `f09f5ae` and deployed the latest lineup and match-scoring fixes to the Canada Central Azure App Service; package excluded runtime databases, uploads, duplicates, and secrets.
- 2026-10-31: Deployed the latest `main` code to the Canada Central Azure App Service after compile and scorecard-reader checks; package excluded runtime databases, uploads, and secrets.
- 2026-10-29: Standardized page titles at a smaller, professional size across the shared sports system, Home, Rankings, Sign In, Quick Score, and pricing pages.
- 2026-10-29: Halved the page-title font sizes across desktop and phone layouts in response to feedback that titles were still too large.
- 2026-10-29: Deployed the halved page-title sizes to the existing Canada Central Azure App Service; runtime databases, uploads, and secrets were excluded from the package.
- 2026-10-29: Broadened `.gitignore` to exclude all `app/data/*.db*` files and sidecars; removed the tracked local database from the pending merge while preserving its on-disk copy.
- 2026-10-28: Removed the duplicate season badge from signed-in Home and retained the selected season year as the single hero title.
- 2026-10-28: Redeployed the latest application package to Azure App Service, excluding databases, uploads, and secrets. Enabled the system-assigned managed identity, granted least-privilege Key Vault Secrets User access, and configured the Gemini key as a versionless Key Vault reference. Production health and Gemini reader checks passed; synthetic scorecard extraction returned 17 runs. Production data remains on persistent SQLite pending the backed-up Azure SQL migration.
- 2026-10-28: Restarted the local app against `app/data/cricketclubapp.db`, verified health, and successfully extracted a synthetic test scorecard through Gemini using the local API key. The initial production check found the basic reader and no Key Vault identity; these Gemini deployment gaps were fixed later the same day. Azure SQL migration remains pending.
- 2026-10-28: Provisioned the free-limit production Azure SQL PaaS database and replacement Key Vault in Canada Central; copied the Gemini secret. The SQL database remains empty and the live app remains on SQLite until SQL-compatible code and a backed-up, verified data migration are ready. Test remains SQLite.
- 2026-10-28: Soft-deleted the former East US Key Vault `testkeyvault179` after confirming the Gemini secret is present in the Canada Central replacement; Azure retains it for 90 days before permanent purge.
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
- 2026-10-30: Merged Amit's smaller page titles (Oct 29, halved title sizes) with the Roboto font change: titles keep Amit's sizes and use Roboto; changed CSS / app.js have version 20261030m. The local database is no longer in git (Amit's .gitignore).
- 2026-10-30: "Match not found." on Save line-ups (req 169): the match was saved, but a second copy of the app was still running on port 8090 from an old window, and on Windows the two copies answer requests in turn - the old one didn't know the new match. `python app\main.py` now refuses to start when the app is already running on that port and says to close the other window.
- 2026-10-31: Full scoring check before the Saturday match (req 170): a whole club match was played through the Score page on a phone-sized screen - 11 + 11 line-ups with captain / keeper, runs, wide, no ball +4, leg byes, byes, bowled, caught, run out (non-striker, 1 run), stumped, fixing a ball, undo, bowler changes, innings break, chase, win - and every total checked against the server, the public page and the scorecard (49 checks). Three problems found and fixed:
  - Undo while the next ball was being saved could bring the undone ball back (two saves at once, one lost). Scoring saves now go one at a time (`_scoring_locked` in `main.py`: a threading lock plus an SQLite write lock on `cricketclubapp.db.scorelock`, so it also works with several Azure workers), and the Score page refuses a new ball until Undo or a fix has saved ("One moment, still saving the last change"). 12 balls sent at the same moment: all 12 saved.
  - The public page stopped refreshing at the innings break (nothing was "live"), so followers never saw the chase start. It now keeps checking until the match is finished (every 10 s once started, every 30 s before the first ball).
- 2026-10-31: A finished match's public page has no Live tab - just Scorecard and Commentary, opening on the Scorecard (req 171). `public_match.js` / `quick_score.js` 20261031a.
- 2026-10-31: Scorecard check (req 172): the list and its filters, every published scorecard on a phone and a laptop, upload -> type in -> publish -> page with a card whose every number is known (all rows, "c & b", strike rates, extras, total, did not bat, bowling, match details, photo tab, duplicate photo refused), and a scored match's scorecard (totals, fall of wickets, every ball in Commentary) - 33 checks. Fixed: a long team name ("Toronto Community Cricket Club Innings") made the innings bar wider than a phone and cut off the SR / Econ columns and the extras number; the name now shortens with "..." and the tables fit (`public_match.css` 20261031b). Found in the data: the Coca Cola XI vs TPC card (29 Sep 2024) adds up to 160, not 161 - check it against its photo.
- 2026-10-31: Second full check (req 173): the full match again (49 checks), the scorecards again, and new cases - the other team batting first, all out with 3 players, a tie ("WHAT A FINISH!"), swap strike, changing the bowler mid-over, typed balls ("4 wd 2"), the server going down mid-over (the 3 balls tapped meanwhile were saved once it was back, none twice), a guest match with no sign-in, and every page on a phone and a laptop (signed in and not). Fixed a serious bug: when the other team batted first, Heartlake's chase was saved as the other team batting again, so the target, the scorecard and the result were wrong. The store treated "Heartlake Cricket Club" as a placeholder name and replaced it (`normalize_innings_scorebook` in `cricket_store.py`); now only an empty name, "club" or "heartlake" is filled in. Her saved matches were not affected (Heartlake batted first in all of them). The old repo tests (`tests/test_local_qa.py`) fail the same way before and after today's changes: they need test accounts this database doesn't have.
- 2026-10-31: Line-ups (req 174): a player ticked and also typed / pasted in "Other players" (e.g. the WhatsApp list pasted after ticking the same players) counted twice, so 11 players showed as 21. Each name now counts once (any spelling of capitals). Over 11, the count turns red and the message says how many are ticked and how many typed and how many to remove ("Heartlake Cricket Club: 21 players (11 ticked + 10 in "Other players"). Keep 11 at most: untick or delete 10."). `quick_score.js` / `.css` 20261031c.
- 2026-10-31: Afghan Eagles match (req 175, /live/b843f79c on Azure): Azure still had the bug fixed earlier today where "Heartlake Cricket Club" counted as a placeholder team name. The match was saved as "Afghan Eagles bowled to Afghan Eagles" and Heartlake's chase as Afghan Eagles batting again, so the Score page offered the 1st innings players and the scorer typed the bowler by hand ("Parvez" next to "Parwez"). Fixes:
  - Matches already saved like that are put right as they are read: a team never bowls to itself and the two innings are always different teams (`_repair_scorebook_teams` in `cricket_store.py`). Tested by breaking a match the same way.
  - A batter or bowler typed in on the day joins their team's line-up (up to 11), so the pick lists show them next time and "all out" counts them (`_grow_lineups_with_new_players` in `main.py`; the Score page now sends the new batter with a wicket). In that match "Ab" batted without being in the line-up.
  - Tested: other team batting first, a typed-in batter, all out at the right wicket, the chase lists (Heartlake batters, their bowlers), the phone's Back button in the middle of the chase, and the public page. `quick_score.js` 20261031d.
- 2026-11-11: Player names on the Home page (rankings, leaderboards, player search, follow list, selected player, team player scores, scorebook pair, suggested performances) link to the player profile `/players/<player id>`. `app.js` has `playerNameLink` (uses `findMemberByName`; plain text when the name is not a stored member); `styles.css` `.player-profile-link`; `index.html` app.js v20261111a, styles.css v20261111a.
- 2026-11-11: Focused club snapshot "Top Batter" links to the profile. Batting, bowling and fielding ranking cards (Ranking page) and the Home rankings preview all show the player's batting, bowling and fielding totals through `rankingStatsHtml` in `app.js`. `index.html` app.js v20261111b.
- 2026-11-13: Batting, bowling and fielding are kept apart in ranking cards. Cards (Ranking page and Home preview) show only their own category: batting cards show matches, runs, average and strike rate; bowling cards show wickets and per match; fielding cards show catches and per match (`rankingStatsHtml(item, category)` in `app.js`). `app.js` v20261113b.
- 2026-11-13: `/players/<player id>` season and club stats are one row each, grouped as Batting | Bowling | Fielding under a group header. Each group is a tinted tile, with gap cells between tiles (`statRows` in `player_public.js`; `.pm-profile` rules in `public_match.css`). The profile is left aligned, full width (max 1040px), and has more space between sections. Columns: M, Runs, HS, Avg, SR | Ov, Wkts, Econ | Ct. `player_public.js` v20261113g, `player_public.html` loads `public_match.css` v20261113g and has class `pm-profile`. Checked in the browser at 1280px (no overflow) and 390px (table scrolls inside its box, page does not overflow).
- 2026-11-13: `/players/<player id>` fielding shows catches (C) and run outs (RO) as columns after the Fielding band, with C and RO headers centred and values right aligned. Run outs come from scorecard dismissals "run out (Fielder)" and are counted per fielder, season and club by `_member_run_outs` in `main.py` (returned as `fielding`). Also added a Run outs tile. `player_public.js` v20261113h, `public_match.css` v20261113g. Verified at 1280px and 390px. Haris (1084) has 0 run outs in the stored data.
- 2026-11-11: `/players/<player id>` recent matches use the same Batting | Bowling | Fielding bands as the season and club tables (R, B, SR | Ov, W, R | C, RO), one row per match. `_member_match_fielding` in `main.py` counts catches ("c X b Y", "c & b Y") and run outs per scorecard, returned in each `recent` item as `fielding`. Summary tiles have a colour per group (blue batting, orange bowling, green fielding) and larger figures. Numeric cells are right aligned. `player_public.js` v20261113i, `public_match.css` v20261113i, `player_public.html` loads both. Verified at 1280px (no overflow) and 390px (document 375px, tables scroll inside their boxes).
 a Bowling table for Career, Season by season and By club (Inns, Overs, Mdns, Runs, Wkts, Avg, Econ, Best). Bowling comes from the scorecards (`public_player_profile` in `main.py` aggregates each innings' bowling row). Batting tables keep Ct (catches) as the fielding figure; Wkts moved to the bowling table. Stumpings are not recorded anywhere in the app, so they are not shown. `player_public.js` v20261112a.
- 2026-11-13: Home page caching. `multipage.js` has `cachedPageLoad(key, load, render)` (stale-while-revalidate in sessionStorage, keys prefixed `cricketClubAppPageCache:`) and `clearPageCache()`, which runs when the auth token changes. `app.js` `loadDashboard` caches `/api/dashboard` (`showCached: false` after a fixture delete). `dashboard_home.js` caches the Home feeds (live, fixtures, scorecards, club, scorebook edit rights) and re-renders through `selectHome`/`renderHome`. `index.html`: multipage.js and app.js v20261113a, dashboard_home.js v20261113a. Not yet tested in a browser (sign-in required).
- 2026-11-13: Clubs page player snapshot shows bowling. Year wise and Club wise tables gained Ov, Wkts and Econ after St, with a Batting / Fielding / Bowling band row. Backend: `_member_bowling_breakdown` in `main.py` aggregates scorecard bowling by season and club for the signed-in member, returned as the `bowling` key of `player_profile_data` (feeds `/api/player/summary`). `clubs.js` `bowlingByYear` / `bowlingByClub`; `clubs.html` loads `clubs.js?v=20261111a` and `styles.css?v=20261111a`; `.snapshot-band` added to `styles.css`. Not yet verified in a browser (sign-in required).## New UI Look and Feel

## 1. Typography & Global Layout Foundation
Prompt for Copilot Chat / Panel:

> Write a clean, modular CSS layout configuration for a premium light-themed sports website canvas. Import "Anton", "Inter", and "Space Mono" from Google Fonts. Set the global background canvas color to an off-white `#F8F9FA` and default text to `#1A1A1A`. Create two primary structural heading classes:
> 
> 
> 1. `.sports-title`: Uses the font 'Inter', a clear medium-sized heading, and restrained letter spacing for a professional page title.
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
