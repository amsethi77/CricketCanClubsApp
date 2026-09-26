Here is a production-grade Codex design specification `.md` direction for the new:

* Public Live Matches
* Anonymous Scorecard Viewing
* Login/Register Integration
* Read-only Live Match Center
* Mobile-first sports UX

This should become something like:

```text
/PUBLIC_LIVE_MATCHES_DESIGN.md
```

# PUBLIC LIVE MATCHES & READ-ONLY SCORECARD DESIGN — CODEX IMPLEMENTATION GUIDE

---

# FEATURE OVERVIEW

The platform MUST support public anonymous access to:

* live matches
* live scorecards
* innings summaries
* commentary
* batting cards
* bowling cards
* partnerships
* match timeline

Anonymous users MUST NOT:

* score matches
* modify scorecards
* edit commentary
* access admin tools
* access squad management
* access availability management

This feature transforms the platform from:

* a private scoring tool

into:

* a public cricket ecosystem platform

similar to:

* Cricbuzz
* CricHeroes
* ESPN CricInfo
* SofaScore

---

# PRODUCT GOAL

The login and registration pages MUST become:

* engaging
* sports-focused
* realtime
* community-oriented

The auth pages MUST NOT feel like:

* enterprise login screens
* boring authentication forms
* admin portals

The experience MUST feel like:

* a live cricket network homepage

---

# PRIMARY UX GOALS

1. Drive anonymous engagement
2. Encourage registrations
3. Showcase live cricket activity
4. Build local cricket community
5. Increase return visits
6. Create premium sports experience

---

# PUBLIC USER CAPABILITIES

Anonymous users MAY:

* view live matches
* view scorecards
* view innings
* view batting cards
* view bowling cards
* view run rates
* view commentary
* view partnerships
* view match summaries
* view player score summaries

---

# PUBLIC USER RESTRICTIONS

Anonymous users MUST NOT:

* score matches
* edit scorecards
* add commentary
* modify players
* modify squads
* modify innings
* access admin center
* access assistant actions
* update availability

---

# LOGIN & REGISTRATION PAGE REDESIGN

The Login/Register page MUST become:

* a sports homepage
* a live match portal
* a cricket discovery screen

---

# PAGE LAYOUT — DESKTOP

---

## | Hero Section        | Login/Register Card     |

## | Live Matches Today                          |

## | Public Match Cards                          |

---

# PAGE LAYOUT — MOBILE

Hero
↓
Live Matches
↓
Public Match Cards
↓
Login/Register CTA

---

# HERO SECTION DESIGN

The hero section MUST include:

Headline:
“Live Local Cricket. Real-Time Scorecards.”

Subheadline:
“Track matches, follow players, and join your club.”

Primary CTA:

* Register
* Login

Secondary CTA:

* View Live Matches

---

# VISUAL STYLE

The page MUST feel:

* premium
* modern
* sports-focused
* mobile-first

---

# DESIGN REFERENCES

Use inspiration from:

* Cricbuzz
* CricHeroes
* Apple Sports
* SofaScore
* IPL App
* ChatGPT mobile

---

# REQUIRED DESIGN ELEMENTS

Use:

* glassmorphism
* live indicators
* floating cards
* soft gradients
* realtime feel
* sports broadcast styling

---

# COLOR SYSTEM

Primary:

* Cricket Red
* Deep Blue
* Emerald Green

States:

* LIVE = Red
* Upcoming = Amber
* Completed = Slate

---

# LIVE MATCHES SECTION

Title:
“🔥 Live Matches Today”

The live matches section MUST:

* auto-refresh
* show realtime data
* prioritize active matches
* support mobile scrolling

---

# MATCH CARD DESIGN

Each match card MUST include:

* live badge
* club names
* current score
* overs
* target
* run rate
* venue
* current status

---

# MATCH CARD EXAMPLE

Heartlake CC
145/4 (18.2)

vs

Toronto Community CC
176/7 (20)

LIVE
RR 7.9

---

# MATCH CARD INTERACTIONS

Anonymous users clicking a match MUST open:

* read-only scorecard mode

---

# PUBLIC SCORECARD PAGE

The public scorecard page MUST feel like:

* Cricbuzz live score
* ESPN CricInfo
* professional sports broadcast

---

# PUBLIC SCORECARD NAVIGATION

Tabs:

[ Scorecard ]
[ Commentary ]
[ Timeline ]
[ Stats ]
[ Partnerships ]

---

# PUBLIC SCORECARD HEADER

Sticky Header Example:

Heartlake CC 145/4
18.2 Overs
LIVE

---

# SCORECARD CONTENT

The public scorecard MUST include:

## Batting Card

* batter names
* runs
* balls
* strike rate
* boundaries

---

## Bowling Card

* overs
* maidens
* wickets
* economy

---

## Match Summary

* target
* run rate
* required rate
* partnerships

---

## Recent Balls

Example:
4 1 W 0 6 WD

---

# COMMENTARY SECTION

Commentary MUST support:

* chronological feed
* ball-by-ball updates
* wicket highlights
* milestones

Anonymous users MUST NOT:

* add commentary
* edit commentary

---

# READ-ONLY MODE

Public pages MUST show:

🔒 Read-only public mode

The UI MUST visually disable:

* score controls
* admin actions
* editing actions

---

# LOCKED FEATURE STRATEGY

When anonymous users attempt:

* scoring
* assistant usage
* squad access

Show modal:

“Register to access club features.”

---

# REGISTRATION CONVERSION STRATEGY

The platform MUST encourage registrations.

Sticky CTA examples:

“Join your club to:
✓ score matches
✓ track stats
✓ update availability
✓ use AI assistant”

---

# PUBLIC NAVIGATION

Anonymous Navigation:

🏠 Home
🔥 Live Matches
📅 Fixtures
🏆 Rankings
🔐 Login
✨ Register

---

# AUTHENTICATED NAVIGATION

🏠 Home
🏏 Match
📅 Fixtures
👥 Squad
🤖 Assistant
⚙ More

---

# MOBILE UX RULES

The public pages MUST:

* prioritize mobile first
* support thumb interaction
* avoid large forms
* use card layouts
* use segmented controls
* use swipe gestures

---

# PUBLIC MATCH FLOW

Anonymous User
↓
View Live Matches
↓
Open Match
↓
Read-only Scorecard
↓
Registration CTA
↓
Register/Login

---

# PUBLIC API DESIGN

Anonymous APIs MUST:

* be read-only
* exclude admin actions
* exclude editing endpoints
* cache aggressively
* support websocket updates

---

# PUBLIC API ROUTES

/api/public/live-matches
/api/public/match/:id
/api/public/scorecard/:id
/api/public/commentary/:id

---

# AUTHENTICATED API ROUTES

/api/v1/scoring
/api/v1/commentary
/api/v1/admin
/api/v1/squad

Authenticated routes MUST require:

* JWT/session auth
* RBAC validation

---

# WEBSOCKET DESIGN

Public websockets MAY support:

* live score updates
* commentary updates
* match state changes

Public websockets MUST NOT:

* allow publishing
* allow scoring actions

---

# PERFORMANCE REQUIREMENTS

Public pages MUST:

* load fast
* support caching
* prioritize mobile rendering
* support realtime updates

---

# SEO REQUIREMENTS

Public live match pages MUST support:

* SEO metadata
* share previews
* OpenGraph cards
* Google indexing

---

# SHAREABLE MATCH LINKS

Public matches MUST support:

* direct URLs
* WhatsApp sharing
* social previews

Example:

/live-match/heartlake-vs-toronto-2026-05-24

---

# PUBLIC MATCH URL STRUCTURE

/live
/live/:match-id
/live/:match-id/commentary
/live/:match-id/stats

---

# REQUIRED UI COMPONENTS

/components/public
PublicMatchCard
LiveBadge
PublicScoreboard
CommentaryFeed
MatchTimeline
PartnershipCard
RegisterCTA

---

# REQUIRED SCREENS

/screens/public
PublicHome
LiveMatches
PublicScorecard
PublicCommentary
PublicStats

---

# ANIMATION STRATEGY

Use:

* subtle score transitions
* live pulse indicators
* smooth card hover effects
* realtime ticker updates

Avoid:

* heavy animations
* distracting motion

---

# LIVE INDICATOR DESIGN

Required states:

🔴 LIVE
🟡 INNINGS BREAK
⚪ COMPLETED
🔵 UPCOMING

---

# FUTURE FEATURES

Future anonymous features MAY include:

* follow clubs
* follow players
* notifications
* AI summaries
* player rankings
* fantasy mode
* season leaderboards

---

# FUTURE AI FEATURES

Public AI features MAY support:

* AI match summaries
* AI innings analysis
* AI player insights
* AI win probability

---

# IMPLEMENTATION PRIORITY

## Phase 1

* public live match cards
* public scorecards
* read-only APIs

## Phase 2

* commentary
* partnerships
* realtime updates

## Phase 3

* AI summaries
* rankings
* social sharing

## Phase 4

* notifications
* follows
* fantasy integration

---

# MOST IMPORTANT PRODUCT RULE

The public experience MUST feel:

* exciting
* realtime
* sports-oriented
* community-driven
* premium

NOT:

* admin-like
* form-heavy
* enterprise-focused

---

# FINAL EXPERIENCE GOAL

The public website should feel like:

Cricbuzz
+
Apple Sports
+
Live Local Cricket
+
Modern Mobile App UX

Combined into:
ONE realtime public cricket ecosystem.

Reference:

* existing FastAPI architecture
* current scoring engine
* current websocket flows
* current live scoring UI
* current OCR architecture
* current mobile-first redesign direction

Codex MUST preserve:

* RBAC
* read-only restrictions
* mobile-first UX
* realtime performance
* public/private route separation


