# CricketCanClubs API (web site and mobile apps)

Every feature of the app works through these JSON APIs - the web pages call them too, so the iOS and Android apps
can do everything the site does. This file is made by `python scripts\api_guide.py` (run it again after adding or
changing an API). The live, clickable version is **/docs** on the running site (for example
https://cricketcanclubs-web.azurewebsites.net/docs), and **/openapi.json** for code generators.

## How to call it

1. Sign in: `POST /api/auth/signin` with `{"identifier": "<mobile or email>", "password": "..."}`. The answer has
   `token`, the `user` (roles, club) and the clubs he can switch to.
2. Send the token on every call as the header `X-Auth-Token: <token>`. A token stays valid until
   `POST /api/auth/signout` or until it is idle too long (then sign in again: the API answers 401).
3. Switch club: `POST /api/auth/select-club` `{"club_id": "..."}` - club pages, stats and admin lists follow the
   current club.
4. Bodies are JSON (`Content-Type: application/json`); photo uploads are `multipart/form-data` (field `file`).
5. Errors: HTTP 4xx with `{"detail": "a message you can show to the person"}`.

Paths starting `/api/public/` need no sign-in. `/api/admin/...` needs a club admin of that club or the superadmin.

## Main screens -> APIs

| Screen | APIs |
| --- | --- |
| Sign in / register | `POST /api/auth/signin`, `GET /api/auth/options`, `POST /api/auth/register`, `GET /api/auth/me` |
| Home | `GET /api/dashboard`, `GET /api/weather?lat=&lon=`, `GET /api/notifications` |
| Scorecards list / one card | `GET /api/public/scorecards`, `GET /api/public/scorecards/{id}` (names carry `tags` C/VC/WK and `playing_role`) |
| Upload a scorecard photo | `POST /api/scorecards/upload` (answers at once, read in the background), then poll `GET /api/scorecards/{id}/processing`, `GET /api/scorecards/{id}/preview` |
| Fix a read card / confirm names | `POST /api/scorecards/{id}/...` (edit, publish, name-identity, people) - see "Scorecards" below |
| Live scoring | `GET /api/public/match/{id}`, `POST /api/matches/{id}/...` (balls, line-ups, man of the match) |
| Stats | `GET /api/rankings`, `GET /api/stats/captains?year=` |
| Admin: clubs, people & roles | `GET /api/admin/club-management`, `GET /api/admin/clubs/{club_id}/people`, `POST .../people/{user_id}/club-role`, `POST .../people/members/{member_id}/playing-role` |
| Admin: duplicates | `GET /api/admin/name-matches`, `POST /api/admin/name-matches/reject`, member merges |

## Every API, by feature


### Sign in and accounts (10)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/account/delete` | "Delete my account" on the Profile page (README "Privacy policy and Delete my account"; Apple requires it |
| GET | `/api/auth/me` | Auth Me |
| GET | `/api/auth/options` | Roles, clubs and players for the Register page. |
| POST | `/api/auth/register` | Register |
| GET | `/api/auth/roles` | Auth Roles |
| POST | `/api/auth/select-club` | Select Club |
| POST | `/api/auth/signin` | Signin |
| POST | `/api/auth/signout` | Auth Signout |
| POST | `/api/viewer-profile` | Update Viewer Profile |
| POST | `/api/viewer-profile/follow-player` | Follow Player |

### Admin: clubs, people and roles (15)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/admin/club-management` | Club Management |
| POST | `/api/admin/clubs/merge` | Merge Clubs |
| GET | `/api/admin/clubs/merge-preview` | Club Merge Preview |
| DELETE | `/api/admin/clubs/{club_id}` | Delete Club |
| POST | `/api/admin/clubs/{club_id}/delete` | Delete Club Form |
| GET | `/api/admin/clubs/{club_id}/delete-check` | Delete Club Check |
| POST | `/api/admin/clubs/{club_id}/disable` | Disable Club Form |
| POST | `/api/admin/clubs/{club_id}/enable` | Enable Club Form |
| DELETE | `/api/admin/clubs/{club_id}/fixtures/{fixture_id}` | Delete Season Fixture |
| PUT | `/api/admin/clubs/{club_id}/fixtures/{fixture_id}` | Update Season Fixture |
| DELETE | `/api/admin/clubs/{club_id}/members/{member_id}` | Delete Club Member |
| POST | `/api/admin/clubs/{club_id}/members/{member_id}/delete` | Delete Club Member Form |
| GET | `/api/admin/clubs/{club_id}/people` | Club People |
| POST | `/api/admin/clubs/{club_id}/people/members/{member_id}/playing-role` | Set Playing Role |
| POST | `/api/admin/clubs/{club_id}/people/{user_id}/club-role` | Set Club Role |

### Admin: duplicate players (AI name check) (8)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/admin/member-merges/{merge_id}/undo` | Admin Undo Member Merge |
| GET | `/api/admin/merge-requests` | Admin Merge Requests |
| POST | `/api/admin/merge-requests/{request_id}/decision` | Admin Decide Merge Request |
| GET | `/api/admin/name-claims` | Admin Name Claims |
| POST | `/api/admin/name-claims/{claim_id}/decision` | Admin Decide Name Claim |
| GET | `/api/admin/name-matches` | Admin Name Matches |
| POST | `/api/admin/name-matches/merge` | Admin Merge Members |
| POST | `/api/admin/name-matches/reject` | Admin Reject Name Match |

### Admin: scorecard review (12)

| Method | Path | What it does |
| --- | --- | --- |
| DELETE | `/api/admin/archive/{upload_id}` | Delete Archive |
| POST | `/api/admin/archive/{upload_id}/approve` | Approve Archive |
| POST | `/api/admin/archive/{upload_id}/approve-form` | Approve Archive Form |
| POST | `/api/admin/archive/{upload_id}/review` | Save Archive Review |
| POST | `/api/admin/archive/{upload_id}/review-form` | Save Archive Review Form |
| GET | `/api/admin/review-queue` | Admin Review Queue |
| GET | `/api/admin/scorecards/checks` | Site admin: uploads waiting for review (with the reasons) and groups of duplicate uploads. |
| POST | `/api/admin/scorecards/duplicates/ai-scan` | Ask the AI about likely pairs the simple checks didn't catch (same day, or a shared team with a total |
| POST | `/api/admin/scorecards/duplicates/hide` | Mark uploads as duplicates. Nothing is deleted: they just drop out of Scorecards, stats and the queue. |
| GET | `/api/admin/scorecards/reread-all` | Admin Reread All Status |
| POST | `/api/admin/scorecards/reread-all` | Site admin: start the clean-up + AI re-read of every scorecard photo (background). |
| POST | `/api/admin/scorecards/{upload_id}/decision` | Admin Scorecard Decision |

### Admin: photos and storage (2)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/admin/uploads/shrink` | Admin Shrink Photos |
| GET | `/api/admin/uploads/storage` | Admin Photo Storage |

### Admin: backups and database (5)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/admin/backups` | Admin Backups |
| POST | `/api/admin/backups` | Admin Backup Now |
| GET | `/api/admin/backups/{file_name}` | Admin Backup Download |
| GET | `/api/admin/db/export` | Export Database |
| POST | `/api/admin/db/import` | Import Database |

### Admin: WhatsApp alerts (2)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/admin/whatsapp` | Admin Whatsapp Status |
| POST | `/api/admin/whatsapp/test` | Send one WhatsApp now to check the setup: Meta's ready-made "hello_world" (works as soon as the token and number |

### Admin: costs and AI accuracy (3)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/admin/ai-accuracy` | Superadmin: how often the AI reader was right, overall, by kind of field, by month and per card. |
| GET | `/api/admin/costs` | Superadmin: this month's (or ?month=YYYY-MM) AI calls, WhatsApp messages and estimated cost, plus the last 6 |
| POST | `/api/admin/costs/rates` | Superadmin: save the prices the cost estimate uses (from the Google, Meta and Azure bills). |

### Admin: other (5)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/admin/audit-log` | Admin Audit Log |
| GET | `/api/admin/subscriptions` | Admin Subscriptions |
| POST | `/api/admin/subscriptions/set` | Admin Set Subscription |
| GET | `/api/admin/traffic` | Admin Traffic |
| DELETE | `/api/admin/users/{user_id}` | Site admin: delete a sign-in account (e.g. test accounts before launch). The player record (member) |

### Scorecards: upload, read with AI, edit, publish (20)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/archive/reset-scores` | Reset Scores |
| POST | `/api/archive/{upload_id}/apply` | Apply Archive |
| POST | `/api/archive/{upload_id}/extract` | Extract Archive |
| POST | `/api/archive/{upload_id}/import-extraction` | Import Archive Extraction |
| GET | `/api/scorecards/reader` | Which photo reader the upload page will use (shown on /scorecards/upload). Plan-aware: |
| POST | `/api/scorecards/upload` | Upload Scorecard |
| POST | `/api/scorecards/{upload_id}/ai-read` | "🤖 Read with AI": (re)read an existing upload's photo with the AI vision model. |
| POST | `/api/scorecards/{upload_id}/join/{other_id}` | "🔗 Join the two innings": two uploads that are the two innings of one match become one scorecard. |
| POST | `/api/scorecards/{upload_id}/link` | Nov 2 2026 (Amit): link this upload to the other team's innings by its Match ID, so the match has both |
| POST | `/api/scorecards/{upload_id}/manual` | "Type in the scorecard": the uploader, their club's scorers or a site admin enter the card by hand |
| POST | `/api/scorecards/{upload_id}/name-identity` | 'Yes, Amit on this card is Amit S': remember it for the club and write it on the card (and its stats). |
| POST | `/api/scorecards/{upload_id}/name-identity-reject` | 'No, Amit on this card is not Amit G' (or none of the players shown): remember it, don't suggest it again. |
| POST | `/api/scorecards/{upload_id}/name-merge` | Merge two players that this scorecard's names show are the same person. Keeps the older or newer record. |
| POST | `/api/scorecards/{upload_id}/people` | Nov 11 2026 (Amit: "please add the captains from each side and the man of the match in the match Result |
| GET | `/api/scorecards/{upload_id}/preview` | The full digital scorecard of an upload that isn't published yet (uploader, own club's scorers, site admins). |
| GET | `/api/scorecards/{upload_id}/processing` | Is this upload still being read? (The preview page asks every few seconds while it is.) |
| POST | `/api/scorecards/{upload_id}/publish` | The scorer checked the digital scorecard and it looks right: publish it (no admin needed when the checks passed). |
| POST | `/api/scorecards/{upload_id}/remove-duplicate/{other_id}` | "🗑 Delete the duplicate": the other upload holds the same innings as this one, so it is removed (with its |
| POST | `/api/scorecards/{upload_id}/report` | "Something's wrong": send the upload to the site admins with a note, and tell the club's players. |
| POST | `/api/scorecards/{upload_id}/second-photo` | Amit, Nov 2 2026: a scorecard photographed on two pages. When the upload has only one innings, the uploader, |

### Scorecards: view (3)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/public/scorecards` | Approved scorecards; signed-in users are scoped to their club except superadmins. |
| GET | `/api/public/scorecards/{scorecard_id}` | Public Scorecard Detail |
| GET | `/api/public/scorecards/{scorecard_id}/scorecard.pdf` | Nov 17 2026 (Amit: "we should have a PDF also to download ... for both uploaded as well as for online games"): |

### Matches and live scoring (26)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/guest/matches` | Guest Match Create |
| GET | `/api/guest/matches/{match_id}` | Guest Match State |
| DELETE | `/api/guest/matches/{match_id}/ball` | Guest Match Undo |
| POST | `/api/guest/matches/{match_id}/ball` | Guest Match Ball |
| POST | `/api/guest/matches/{match_id}/setup` | Guest Match Setup |
| GET | `/api/guest/resume` | Guest Match Resume |
| POST | `/api/matches/{match_id}/ai-scorer` | Pro AI Live Scorer (or a Free user's one free AI match): phrase -> validated ball events. The client posts each event to /scorebook/ball. |
| POST | `/api/matches/{match_id}/availability` | Update Availability |
| POST | `/api/matches/{match_id}/commentary` | Add Commentary |
| POST | `/api/matches/{match_id}/details` | Update Match Details |
| POST | `/api/matches/{match_id}/lineup` | Update Playing Xi |
| POST | `/api/matches/{match_id}/lineups` | Save Match Lineups |
| POST | `/api/matches/{match_id}/man-of-match` | A playing club's captain / club admin or the superadmin picks the man of the match of a scored match. |
| POST | `/api/matches/{match_id}/performances` | Add Performance |
| DELETE | `/api/matches/{match_id}/scorebook/ball` | Delete Scorebook Ball |
| POST | `/api/matches/{match_id}/scorebook/ball` | Add Scorebook Ball |
| POST | `/api/matches/{match_id}/scorebook/edit` | Fix a scored match (README "Edit a scored match", Nov 1 2026): which team batted in each innings, a player's |
| POST | `/api/matches/{match_id}/scorebook/setup` | Update Scorebook Setup |
| POST | `/api/matches/{match_id}/scorecard` | Update Scorecard |
| GET | `/api/public/live-matches` | Public Live Matches |
| GET | `/api/public/live-page` | Public Live Page |
| GET | `/api/public/match/{match_id}` | Public Match |
| GET | `/api/public/match/{match_id}/scorecard.pdf` | Public Match Scorecard Pdf |
| GET | `/api/quick-score/fixtures` | Quick Score Fixtures |
| POST | `/api/quick-score/start` | Create a fixture for today so scoring can start straight away. |
| GET | `/api/quick-score/{match_id}` | Quick Score State |

### Fixtures and availability (3)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/public/fixtures-page` | Public Fixtures Page |
| GET | `/api/season-setup/data` | Season Setup Data |
| POST | `/api/season-setup/fixtures` | Create Season Fixture |

### Players and profiles (15)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/members` | Create Member |
| POST | `/api/members/{member_id}` | Update Member |
| POST | `/api/player/availability` | Save Player Availability |
| GET | `/api/player/availability-data` | Player Availability Data |
| GET | `/api/player/merge-candidates` | Other player records whose name is 75% or more similar, plus this player's own merge requests. |
| GET | `/api/player/merge-candidates/{target_member_id}/details` | Full profile of one suggested player, limited to records that are valid suggestions for the caller. |
| POST | `/api/player/merge-requests` | A player asks for two records of the same person to be merged. Only a club admin or superadmin decides. |
| POST | `/api/player/merge-suggestions/{target_member_id}/dismiss` | Remember that this player rejected a similar-name suggestion so it stops showing. |
| GET | `/api/player/name-suggestions` | Player Name Suggestions |
| POST | `/api/player/name-suggestions/claim` | Player Claim Name |
| POST | `/api/player/profile` | Save Player Profile |
| GET | `/api/player/profile-data` | Player Profile Data |
| POST | `/api/player/season-availability` | Save Player Season Availability |
| GET | `/api/player/summary` | Player Summary Data |
| GET | `/api/public/players/{player_key}` | Public Player Profile |

### Stats and rankings (3)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/public/rankings-chart` | Public Rankings Chart |
| GET | `/api/rankings` | Rankings |
| GET | `/api/stats/captains` | Captain Stats |

### Home and dashboard (5)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/dashboard` | Dashboard |
| GET | `/api/insights/club/{club_key}` | Insights Club |
| GET | `/api/insights/me` | Signed-in user's own form/prediction/tips plus their current club's outlook. |
| GET | `/api/insights/player/{player_key}` | Insights Player |
| GET | `/api/weather` | Nov 14 2026 (Amit: "Isn't there an api to identify the location?"): the browser's location (lat / lon, asked |

### Notifications (2)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/notifications` | Notifications List |
| POST | `/api/notifications/read` | Notifications Read |

### Clubs (3)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/clubs/{club_id}/settings` | Club Settings |
| POST | `/api/clubs/{club_id}/settings` | Save Club Settings |
| GET | `/api/public/clubs` | Read-only club directory for the public Clubs page (no player contact details). |

### Leagues (12)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/leagues` | List Leagues |
| POST | `/api/leagues` | Create League |
| GET | `/api/leagues/choices` | Leagues for the 'League (optional)' pickers; with club_id, only leagues that club is in. |
| DELETE | `/api/leagues/groups/{group_id}` | Delete League Group |
| POST | `/api/leagues/groups/{group_id}/teams` | Add League Team |
| DELETE | `/api/leagues/groups/{group_id}/teams/{club_id}` | Remove League Team |
| DELETE | `/api/leagues/{league_id}` | Delete League |
| POST | `/api/leagues/{league_id}` | Update League |
| GET | `/api/leagues/{league_id}/candidates` | Played matches between two of the league's teams that aren't in any league yet (superadmin 'Add a played match'). |
| POST | `/api/leagues/{league_id}/groups` | Add League Group |
| POST | `/api/leagues/{league_id}/matches` | Add League Match |
| DELETE | `/api/leagues/{league_id}/matches/{match_ref}` | Remove League Match |

### AI assistant (11)

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/chat` | Chat |
| POST | `/api/llm/cache/clear` | Llm Clear Cache |
| GET | `/api/llm/documents` | Llm Documents |
| POST | `/api/llm/infer` | Llm Infer Endpoint |
| GET | `/api/llm/prompts` | Llm Prompts |
| POST | `/api/llm/reindex` | Llm Reindex |
| GET | `/api/llm/status` | Llm Status |
| POST | `/api/muse` | AI Assistant: carries out commands (with a Confirm step) and answers everything else with the LLM assistant. |
| POST | `/api/muse/confirm-score` | Muse Confirm Score |
| POST | `/api/muse/execute` | Carry out a task the AI Assistant planned, after the person tapped Confirm. Everything is checked again here. |
| POST | `/api/public/muse` | Public Muse |

### Plans and payments (5)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/plans` | Plans Catalog |
| POST | `/api/stripe/webhook` | Stripe Webhook |
| POST | `/api/subscription/checkout` | Subscription Checkout |
| GET | `/api/subscription/me` | Subscription Me |
| POST | `/api/subscription/portal` | Subscription Portal |

### Public (no sign-in) (4)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/public/config` | Small switches the pages need. subscriptions=False: launch mode, everyone on Pro, Plans hidden. |
| GET | `/api/public/guest-matches` | Today's guest matches for the public Live page (no codes, no private data). |
| GET | `/api/public/search` | Navbar search: players, clubs and matches. Public data only (no phone, email or age). |
| GET | `/api/public/signin-stats` | Public Signin Stats |

### Other (4)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/cache-status` | Cache Status |
| GET | `/api/health` | Health |
| GET | `/api/tour` | Tour Status |
| POST | `/api/tour/seen` | Tour Seen |

178 APIs.
