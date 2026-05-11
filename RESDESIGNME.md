# CricketCanClubsApp — Unified Master Architecture, Design, AI & Solution Blueprint For Codex

---

# PLATFORM VISION

CricketCanClubsApp is a:

* mobile-first cricket operating platform
* AI-powered local cricket ecosystem
* live scoring engine
* OCR archive platform
* club collaboration system
* player analytics platform
* assistant-driven cricket intelligence system

The system MUST support:

* Web
* PWA
* iOS
* Android
* Offline-first operation

The platform MUST feel like:

* CricHeroes
* Apple Sports
* SofaScore
* IPL mobile app
* ChatGPT mobile assistant

The platform MUST NOT feel like:

* enterprise admin software
* CRUD dashboards
* desktop-only portals

---

# CORE PRODUCT PHILOSOPHY

The application is NOT:

* a giant dashboard
* a form-heavy admin portal
* a desktop enterprise application

The application IS:

* a cricket operating system
* a mobile-first sports platform
* a contextual AI assistant
* a live scoring engine
* a local cricket social ecosystem

---

# PRIMARY PRODUCT GOALS

1. Mobile-first UX
2. Native iOS/Android experience
3. Fast live scoring
4. Offline-first recovery
5. AI-first assistant workflows
6. Multi-club architecture
7. OCR scorecard recovery
8. Club-local analytics
9. Cross-club player intelligence
10. Modern consumer-grade design

---

# CURRENT LOCAL IMPLEMENTATION SNAPSHOT

The local app has been redesigned around a shared header and a cleaner menu split. This is the current working map:

* Shared header fragment: `app/static/shared_header.html`
* Main menu order: `Home | Clubs | Live | Fixtures | Availability | Archives | Performances | AI Assistant | Admin Center`
* Home only: season overview, snapshot cards, club summary, upcoming match summary
* Live: scorecard and commentary only
* Fixtures: create, update, delete fixtures; selected fixture availability board; playing XI selection from the same fixture roster
* Availability: player self-service availability by fixture using three buttons
* Archives: season selection, upload scorecards, archive status, pending review filters
* Performances: player profile view/edit, selected player details, all-year match history, club-wise and season-wise stats
* Clubs: shared player summary and match history view synced with Performance and Player Profile
* AI Assistant: chat-only view, without schedule or ranking panels
* Admin Center: only visible to superadmin

Shared APIs currently being used for consistency and future mobile reuse:

* `GET /api/player/summary`
* `GET /api/player/profile-data`
* `GET /api/dashboard`

Important rules:

* No Azure deploy until the local app is reviewed and approved
* Home-only widgets must not appear on other pages
* Selected club must stay session-scoped and consistent across pages
* Player history shows only played/reviewed fixtures, not pending matches
* The archive history logic must keep the six approved records in sync across Clubs, Performance, and Player Profile

---

# BUSINESS REQUIREMENTS

## Club & Player Management

* Team member profiles
* Player images
* Player age
* Player aliases
* Multiple club memberships
* Club search
* Club creation
* Club admin roles
* RBAC support
* Player following
* Multi-club profiles
* Local cricket ecosystem support

---

## Match & Scoring

* Live scoring
* Ball-by-ball scoring
* 11 batters
* 11 bowlers
* Multiple innings
* Voice scoring
* Text commentary
* Offline recovery
* Match archive
* Playing XI selection
* Commentary persistence

---

## OCR & Archives

* Upload scorecard images
* HEIC conversion
* PNG/JPG optimization
* OCR extraction
* Duplicate detection
* Manual review
* Historical season support
* Player auto-linking
* Scorecard reconstruction

---

## Scheduling & Availability

* Multi-season scheduling
* Upcoming fixtures
* Availability tracking
* Season management
* Playing XI workflows
* WhatsApp reminders

---

## AI & Analytics

* Local LLM integration
* Ollama support
* RAG architecture
* Predictive analytics
* Player rankings
* Club analytics
* Match predictions
* Captain recommendations
* Reliability scoring
* Availability intelligence

---

# TARGET USER TYPES

## Player

* View matches
* Update availability
* View stats
* Follow players
* Use assistant

---

## Captain

* Select playing XI
* Send alerts
* Score matches
* Manage squad

---

## Club Admin

* Configure seasons
* Manage fixtures
* Manage players
* Upload archives

---

## Super Admin

ONLY:

* Amit S
* Amit Sethi

MUST be Super Admin.

Super Admin capabilities:

* global visibility
* OCR review
* scorecard approval
* platform moderation
* multi-club administration

---

# TECHNOLOGY STACK

## Frontend

* React
* TailwindCSS
* Framer Motion
* Capacitor
* PWA support

---

## Backend

* FastAPI
* Python
* SQLite initially
* PostgreSQL future

---

## AI Stack

* Ollama
* Local LLM
* RAG pipelines
* Embedding search
* Prompt registry
* Context retrieval

---

## OCR Stack

* Tesseract
* OpenCV
* Azure Document Intelligence optional

---

## Realtime

* WebSockets
* Background sync
* Live scoring streams

---

## Offline

* IndexedDB
* Offline queues
* Sync recovery

---

# RECOMMENDED FRONTEND STRUCTURE

/frontend
/components
/layouts
/screens
/features
/hooks
/services
/stores
/assistant
/archive
/offline
/navigation
/scoring
/notifications

---

# RECOMMENDED BACKEND STRUCTURE

/backend
/api
/models
/services
/repositories
/assistant
/analytics
/ocr
/notifications
/sync
/ranking
/auth

---

# FEATURE MODULE DESIGN

Every module MUST:

* own its UI
* own its state
* own its APIs
* own its offline queue
* be independently testable

---

# FEATURE MODULES

/features
/auth
/clubs
/matches
/fixtures
/availability
/scoring
/scorebook
/assistant
/archive
/ocr
/players
/rankings
/notifications
/admin

---

# APP SHELL ARCHITECTURE

The application MUST use an App Shell pattern.

---

# APP SHELL RESPONSIBILITIES

/layouts/AppShell

Responsibilities:

* bottom navigation
* top navigation
* floating assistant
* session validation
* offline detection
* sync state
* notifications
* active season
* active club

---

# GLOBAL APPLICATION STATE

The following MUST be globally accessible:

* authenticated player
* selected club
* selected season
* active match
* assistant state
* offline state
* sync queue
* permissions

---

# STATE MANAGEMENT RULES

State MUST NOT:

* live in DOM
* rely on HTML state

State MUST:

* use centralized stores
* use isolated feature stores
* support offline recovery

---

# GLOBAL STORE STRUCTURE

/app-store
auth
activeClub
activeSeason
currentMatch
assistant
notifications
preferences
offlineSync

---

# MOBILE-FIRST DESIGN SYSTEM

The UI MUST feel:

* native
* modern
* sports-focused
* AI-enhanced

---

# DESIGN REFERENCES

Use inspiration from:

* CricHeroes
* Apple Sports
* SofaScore
* IPL App
* ChatGPT Mobile
* Notion Mobile

---

# UI PRINCIPLES

## Required

* glassmorphism
* floating cards
* large touch controls
* sticky actions
* contextual UI
* minimal typing
* smooth transitions
* swipe gestures

---

## Forbidden

* giant dashboards
* giant forms
* dense enterprise tables
* multi-thousand pixel scrolling pages
* horizontal mega navs

---

# MOBILE NAVIGATION ARCHITECTURE

## Primary Bottom Navigation

🏠 Home
🏏 Match
📅 Fixtures
👥 Squad
🤖 Assistant

---

# SECONDARY NAVIGATION

Inside “More”:

* Admin Center
* OCR Uploads
* Notifications
* Archive
* Profile
* Settings

---

# ROUTE ARCHITECTURE

/dashboard
/matches
/matches/:id
/scoring
/fixtures
/squad
/player/:id
/archive
/assistant
/settings

---

# HOME SCREEN DESIGN

The Home screen replaces the giant dashboard.

---

# HOME SCREEN CONTENT

* next match
* upcoming fixtures
* club insights
* AI recommendations
* notifications
* recent scorecards
* player snapshot
* live match widgets

---

# HOME SCREEN MUST NOT CONTAIN

* giant forms
* admin controls
* scoring configuration
* archive review tools

---

# MATCH CENTER DESIGN

The Match Center is the MOST IMPORTANT screen.

The Match screen MUST behave like:

* a guided workflow
* a scoring cockpit
* a live sports console

---

# MATCH FLOW

1. Setup
2. Squad
3. Toss
4. Start Match
5. Live Scoring
6. Commentary
7. Summary
8. Archive

---

# MATCH SCREEN NAVIGATION

Use:
[Overview] [Squad] [Scoring] [Stats] [Commentary]

Navigation SHOULD use:

* segmented controls
* swipe gestures
* sticky headers
* floating actions

---

# LIVE SCORING UX

The current scoring UX is too form-heavy.

Replace with:

* scoring pads
* touch-first controls
* delivery shortcuts
* floating actions

---

# REQUIRED LIVE SCORING BUTTONS

0 1 2 3 4 6 W WD NB

---

# LIVE SCORE HEADER

Heartlake 145/4
18.2 Overs
Target 176

---

# REQUIRED SCORING ACTIONS

* Undo Ball
* Correct Ball
* Add Commentary
* Voice Input
* Pause Match
* Save & Next Ball

---

# LIVE SCORING REQUIREMENTS

* one-handed operation
* offline persistence
* instant recovery
* minimal typing
* voice scoring
* realtime sync

---

# SCOREBOOK ARCHITECTURE

The scorebook MUST be canonical.

All scoring derives from:

* deliveries
* innings
* scorebook state

---

# DELIVERY MODEL

Every delivery MUST support:

* over
* ball
* striker
* non-striker
* bowler
* runs
* extras
* wicket
* wicket type
* dismissed player
* fielder
* commentary
* timestamp
* offline sync id

---

# MATCH OBJECT MODEL

Match
├── Teams
├── Playing XI
├── Innings
│    ├── Batters
│    ├── Bowlers
│    ├── Deliveries
│    └── Commentary
├── Availability
├── Scorecards
├── OCR Imports
└── AI Insights

---

# OFFLINE-FIRST ARCHITECTURE

The platform MUST work offline.

---

# OFFLINE FLOW

Scoring
↓
IndexedDB Queue
↓
Offline Cache
↓
Background Sync
↓
Server Persistence

---

# OFFLINE STATUS STATES

🟢 Synced
🟡 Pending Sync
🔴 Sync Failed
⚫ Offline Mode

---

# OFFLINE RULES

If the network disconnects:

* scoring MUST continue
* data MUST persist locally
* sync MUST retry automatically
* users MUST see sync status

---

# PLAYER PROFILE DESIGN

Player profiles MUST feel:

* sports-card based
* mobile-first
* analytics-focused

---

# PLAYER PROFILE MUST INCLUDE

* profile image
* aliases
* multiple clubs
* batting stats
* bowling stats
* fielding stats
* availability history
* rankings
* season stats
* match history

---

# MULTI-CLUB RULES

Players MAY belong to:

* multiple clubs
* multiple teams
* multiple seasons

---

# CLUB DASHBOARD RULES

Club dashboards MUST show:

* club-local rankings
* club-local fixtures
* club-local scorecards
* club-local availability
* club-local stats

Club dashboards MUST NOT show:

* cross-club player career stats

Cross-club stats belong ONLY in Player Profile.

---

# ACTIVE CLUB RULES

The selected club MUST drive:

* rankings
* fixtures
* scorecards
* availability
* player lists
* admin queues
* widgets

The UI MUST NEVER default back to Heartlake unless no club exists.

---

# ACTIVE SEASON RULES

The selected season MUST drive:

* rankings
* fixtures
* scorecards
* stats
* performance
* dashboards

---

# HISTORICAL SEASON MODE

Historical seasons MUST become:

* read-only
* archive mode

Disable:

* scoring
* availability editing
* commentary editing
* fixture editing

Enable:

* analytics
* archives
* historical browsing

---

# AI ASSISTANT ARCHITECTURE

The assistant MUST behave like:

* ChatGPT mobile
* contextual cricket copilot

---

# ASSISTANT FEATURES

The assistant MUST support:

* player analysis
* club analysis
* match summaries
* captain recommendations
* player comparisons
* archive retrieval
* predictive analytics
* batting analysis
* bowling analysis
* availability intelligence

---

# ASSISTANT CONTEXT SOURCES

The assistant MAY use:

* fixtures
* scorecards
* commentary
* performances
* rankings
* OCR archives
* player profiles

---

# RAG ARCHITECTURE

The assistant MUST:

1. Query the database first
2. Retrieve relevant context
3. Pass structured data to the LLM
4. Generate grounded responses

The assistant MUST NOT hallucinate unsupported statistics.

---

# RAG INFERENCE FLOW

Question
↓
Intent Detection
↓
Database Query
↓
Context Retrieval
↓
Prompt Construction
↓
LLM Inference
↓
Safety Validation
↓
Formatted Response

---

# AI SAFETY RULES

The assistant MUST:

* avoid fake statistics
* avoid hallucinations
* explain missing data
* provide confidence
* prefer grounded summaries

---

# PREDICTIVE ANALYTICS

The AI system SHOULD support:

* player forecasting
* captain prediction
* batting consistency
* bowling consistency
* playing XI recommendation
* availability prediction
* club trend analysis

---

# FORECAST RULES

Forecasts MUST:

* use historical trends
* avoid fake precision
* avoid unsupported projections
* fallback to grounded summaries

---

# AI STATUS INDICATOR

Required states:

✅ Solid Green = Connected & idle
🟢 Blinking Green = Thinking
🔴 Blinking Red = Connecting
⛔ Solid Red = Offline

---

# OCR SYSTEM DESIGN

OCR MUST support:

* scorecard extraction
* innings extraction
* player matching
* metadata extraction
* duplicate detection

---

# OCR EXTRACTION FLOW

Upload
↓
HEIC Conversion
↓
Image Optimization
↓
OCR Parsing
↓
Scorecard Structuring
↓
Player Matching
↓
Duplicate Detection
↓
Review Queue
↓
Approval

---

# OCR REVIEW SYSTEM

The Admin Review screen MUST support:

* image preview
* extracted scorecard preview
* player linking
* innings correction
* manual review
* approval workflow

---

# DUPLICATE DETECTION RULES

Duplicates MUST compare:

* image hashes
* teams
* innings totals
* metadata
* dates

Potential duplicates MUST:

* move to review queue
* preserve originals

---

# PLAYER IDENTITY RESOLUTION

Identity resolution MUST support:

* aliases
* full names
* fuzzy matching
* cross-club identity linking

The system MUST NOT rely on:

* hardcoded mappings
* UI labels only

---

# WHATSAPP INTEGRATION

WhatsApp support MUST include:

* fixture reminders
* availability reminders
* playing XI announcements
* result summaries
* score updates

---

# WHATSAPP UX RULES

Use:

* prefilled messages
* mobile deep links
* contextual actions

---

# NOTIFICATION SYSTEM

Notifications MUST support:

* fixtures
* availability reminders
* scorecard approvals
* AI alerts
* announcements

---

# PUSH NOTIFICATION STRATEGY

Future support:

* Firebase Cloud Messaging
* Apple Push Notifications
* Capacitor Push Plugins

---

# DATABASE ARCHITECTURE

## Initial Database

SQLite

## Future Database

PostgreSQL

---

# LONG-TERM DATABASE STRATEGY

Partition by:

* club
* season
* archive year

---

# CORE DATABASE TABLES

* users
* players
* clubs
* teams
* matches
* seasons
* performances
* innings
* deliveries
* scorecards
* commentary
* rankings
* availability
* notifications
* assistant_sessions
* player_aliases
* player_club_memberships

---

# AUTHENTICATION & RBAC

Roles:

* Player
* Captain
* Club Admin
* Super Admin

RBAC MUST support:

* club isolation
* season isolation
* role permissions
* multi-club memberships

---

# SEARCH ARCHITECTURE

Global search MUST support:

* clubs
* players
* scorecards
* commentary
* fixtures

---

# SEARCH UX

Use:

* predictive search
* fuzzy matching
* grouped results
* typeahead

---

# PAGINATION RULES

Never render:

* giant tables
* giant lists

Use:

* load more
* infinite scrolling
* virtualization

---

# PERFORMANCE OPTIMIZATION

The platform MUST:

* lazy load screens
* virtualize lists
* cache rankings
* cache player summaries
* cache archive summaries
* minimize re-renders

---

# CACHE STRATEGY

Cache:

* player summaries
* rankings
* club summaries
* assistant responses
* recent scorecards

Invalidate cache on:

* scoring updates
* player edits
* archive approvals

---

# SECURITY DESIGN

Security MUST include:

* JWT/session auth
* RBAC enforcement
* upload sanitization
* club isolation
* permission validation

---

# API DESIGN RULES

APIs MUST:

* be club-aware
* be season-aware
* validate permissions
* support offline sync

---

# API VERSIONING

Use:
/api/v1/

Future:

* GraphQL optional
* websocket channels

---

# WEBSOCKET STRATEGY

Realtime channels:

* scoring
* commentary
* notifications
* assistant updates

---

# RECOMMENDED COMPONENTS

/components
BottomNav
MatchCard
PlayerCard
ClubCard
ScorePad
AssistantBubble
FloatingActions
RankingCard
FixtureCard
ScoreboardHeader

---

# RECOMMENDED SCREENS

/screens
Home
MatchCenter
LiveScoring
Fixtures
Squad
Assistant
Archive
OCRReview
PlayerProfile
Settings

---

# UI ANIMATION STRATEGY

Use:

* Framer Motion
* spring transitions
* subtle animations
* swipe gestures

Avoid:

* heavy animations
* slow transitions

---

# DESIGN SYSTEM

Typography:

* Inter
* SF Pro style spacing

Theme:

* Apple Sports inspired
* glassmorphism
* dark mode ready

---

# COLOR SYSTEM

Primary colors:

* Cricket Red
* Deep Blue
* Emerald Green

States:

* success green
* warning amber
* error red

---

# DARK MODE SUPPORT

Support:

* light mode
* dark mode
* system theme sync

---

# ACCESSIBILITY REQUIREMENTS

Support:

* large touch targets
* screen readers
* keyboard navigation
* high contrast
* reduced motion

---

# IOS DESIGN RULES

Follow:

* safe areas
* bottom sheets
* segmented controls
* native gestures
* native spacing

---

# ANDROID DESIGN RULES

Follow:

* Material principles
* FAB patterns
* responsive layouts
* swipe gestures

---

# CAPACITOR REQUIREMENTS

The web app MUST:

* work fully in Capacitor
* support offline mode
* support push notifications
* support deep linking

---

# CI/CD STRATEGY

GitHub Actions MUST:

* lint
* test
* build
* deploy
* package mobile builds

---

# TESTING STRATEGY

Required:

* unit tests
* component tests
* OCR tests
* offline recovery tests
* scoring tests
* AI grounding tests

---

# CODING RULES FOR CODEX

Codex MUST:

* read this document first
* follow mobile-first architecture
* avoid giant dashboards
* avoid giant forms
* isolate features
* optimize for touch
* optimize for offline
* use modular components

---

# FORBIDDEN PATTERNS

Codex MUST NOT:

* create giant scrolling dashboards
* expose all forms together
* overload screens
* use desktop-only layouts
* use enterprise admin UX

---

# PREFERRED UI PATTERNS

Codex SHOULD:

* use bottom navigation
* use floating action buttons
* use swipe navigation
* use card-based layouts
* use sticky score headers
* use segmented controls
* use modal sheets

---

# MOST IMPORTANT PRODUCT RULE

This is NOT an admin dashboard.

This is a:

* cricket operating system
* AI-powered cricket platform
* mobile-first sports ecosystem

---

# IMPLEMENTATION ROADMAP

## Phase 1

* modular routing
* bottom navigation
* app shell
* mobile layouts

## Phase 2

* match center redesign
* scoring redesign
* assistant redesign

## Phase 3

* offline sync
* realtime scoring
* IndexedDB recovery

## Phase 4

* OCR automation
* predictive AI
* assistant enhancements

## Phase 5

* Capacitor packaging
* push notifications
* WhatsApp automation

---

# FINAL EXPERIENCE GOAL

The platform should feel like:

CricHeroes
+
Apple Sports
+
ChatGPT Assistant
+
Live Scoring Engine
+
Local Cricket Community Platform

Combined into:
ONE unified AI-powered mobile-first cricket ecosystem.

---

# EXISTING IMPLEMENTATION NOTES

The current implementation already includes:

* TailwindCSS
* multi-page conversion work
* live scoring workflows
* OCR imports
* archive review
* Ollama integration
* RAG flows
* AI assistant
* player availability
* role-based architecture

However the current architecture is still:

* section-heavy
* desktop-oriented
* form-heavy
* giant-page based

The redesign MUST evolve toward:

* modular routes
* native mobile workflows
* contextual screens
* guided match flows
* AI-enhanced UX
* touch-first scoring

Reference:

* existing README requirements
* OCR/RAG implementations
* current repository architecture
* live scoring flows
* role-based club architecture
* Ollama integration
* current FastAPI backend
* current Tailwind frontend

Reference existing repository documentation and prompt registry during implementation.

Sample design
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Heartlake Cricket Club</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

  <style>
    body {
      font-family: 'Inter', sans-serif;
      background: linear-gradient(to bottom, #eef3ff, #f7f9fc);
    }

    .glass {
      background: rgba(255,255,255,0.78);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255,255,255,0.45);
      box-shadow: 0 10px 40px rgba(15,23,42,0.06);
    }

    .score-button {
      min-height: 72px;
    }

    .bottom-safe {
      padding-bottom: env(safe-area-inset-bottom);
    }
  </style>
</head>
<body class="min-h-screen text-slate-900">

  <div class="max-w-md mx-auto min-h-screen relative pb-28">

    <!-- HEADER -->
    <header class="px-5 pt-6 pb-4">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-slate-500">Good evening 👋</p>
          <h1 class="text-2xl font-extrabold mt-1">Amit Sethi</h1>
          <p class="text-sm text-blue-600 mt-1">Heartlake Cricket Club</p>
        </div>

        <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-red-500 to-blue-600 text-white flex items-center justify-center font-bold text-lg shadow-lg">
          AS
        </div>
      </div>
    </header>

    <!-- NEXT MATCH HERO -->
    <section class="px-5">
      <div class="glass rounded-3xl p-5 overflow-hidden relative">

        <div class="absolute top-0 right-0 w-36 h-36 bg-blue-100 rounded-full blur-3xl opacity-50"></div>

        <div class="relative z-10">
          <div class="flex items-center justify-between">
            <span class="text-xs tracking-[0.25em] uppercase text-red-500 font-bold">
              Next Match
            </span>

            <span class="bg-green-100 text-green-700 text-xs font-semibold px-3 py-1 rounded-full">
              Scheduled
            </span>
          </div>

          <h2 class="text-3xl font-extrabold mt-4 leading-tight">
            June 7th vs Carl XI
          </h2>

          <p class="text-slate-500 mt-2">
            Heartlake Grounds • 9:00 AM
          </p>

          <div class="grid grid-cols-3 gap-3 mt-6">
            <div class="bg-white/70 rounded-2xl p-3 text-center">
              <p class="text-xs text-slate-500">Fixtures</p>
              <p class="text-xl font-bold mt-1">15</p>
            </div>

            <div class="bg-white/70 rounded-2xl p-3 text-center">
              <p class="text-xs text-slate-500">Members</p>
              <p class="text-xl font-bold mt-1">25</p>
            </div>

            <div class="bg-white/70 rounded-2xl p-3 text-center">
              <p class="text-xs text-slate-500">Available</p>
              <p class="text-xl font-bold mt-1">6</p>
            </div>
          </div>

          <div class="flex gap-3 mt-6">
            <button class="flex-1 bg-red-600 text-white py-4 rounded-2xl font-semibold shadow-lg shadow-red-200">
              Start Scoring
            </button>

            <button class="px-5 bg-white rounded-2xl border border-slate-200 font-medium">
              Squad
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- QUICK ACTIONS -->
    <section class="px-5 mt-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-bold text-lg">Quick Actions</h3>
        <button class="text-sm text-blue-600 font-medium">View all</button>
      </div>

      <div class="grid grid-cols-2 gap-4">

        <div class="glass rounded-3xl p-5">
          <div class="w-12 h-12 rounded-2xl bg-blue-100 flex items-center justify-center text-2xl">
            🏏
          </div>
          <h4 class="font-bold mt-4">Live Match</h4>
          <p class="text-sm text-slate-500 mt-1">Score ball by ball</p>
        </div>

        <div class="glass rounded-3xl p-5">
          <div class="w-12 h-12 rounded-2xl bg-green-100 flex items-center justify-center text-2xl">
            👥
          </div>
          <h4 class="font-bold mt-4">Availability</h4>
          <p class="text-sm text-slate-500 mt-1">Track player status</p>
        </div>

        <div class="glass rounded-3xl p-5">
          <div class="w-12 h-12 rounded-2xl bg-yellow-100 flex items-center justify-center text-2xl">
            📸
          </div>
          <h4 class="font-bold mt-4">Upload Archive</h4>
          <p class="text-sm text-slate-500 mt-1">OCR scorecards</p>
        </div>

        <div class="glass rounded-3xl p-5">
          <div class="w-12 h-12 rounded-2xl bg-purple-100 flex items-center justify-center text-2xl">
            🤖
          </div>
          <h4 class="font-bold mt-4">Assistant</h4>
          <p class="text-sm text-slate-500 mt-1">AI cricket insights</p>
        </div>

      </div>
    </section>

    <!-- LIVE SCORING -->
    <section class="px-5 mt-8">

      <div class="flex items-center justify-between mb-4">
        <div>
          <p class="text-xs tracking-[0.25em] uppercase text-red-500 font-bold">
            Live Scoring
          </p>
          <h3 class="font-bold text-2xl mt-1">Match Center</h3>
        </div>

        <button class="bg-white border border-slate-200 px-4 py-2 rounded-xl text-sm font-medium">
          Innings 1
        </button>
      </div>

      <!-- SCORE HEADER -->
      <div class="glass rounded-3xl p-5">

        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-slate-500">Heartlake Cricket Club</p>
            <h2 class="text-5xl font-extrabold mt-2">145/4</h2>
            <p class="text-sm text-slate-500 mt-2">18.2 Overs</p>
          </div>

          <div class="text-right">
            <p class="text-sm text-slate-500">Target</p>
            <p class="text-3xl font-bold mt-2">176</p>
            <p class="text-sm text-red-500 mt-2">31 needed</p>
          </div>
        </div>

        <!-- BATTERS -->
        <div class="mt-6 space-y-3">

          <div class="bg-white/80 rounded-2xl p-4 flex items-center justify-between">
            <div>
              <p class="font-semibold">Amit Sethi*</p>
              <p class="text-sm text-slate-500">45 (32)</p>
            </div>

            <div class="text-right">
              <p class="text-sm text-slate-500">SR</p>
              <p class="font-bold">140.6</p>
            </div>
          </div>

          <div class="bg-white/80 rounded-2xl p-4 flex items-center justify-between">
            <div>
              <p class="font-semibold">Raj Singh</p>
              <p class="text-sm text-slate-500">12 (10)</p>
            </div>

            <div class="text-right">
              <p class="text-sm text-slate-500">SR</p>
              <p class="font-bold">120.0</p>
            </div>
          </div>

        </div>

        <!-- BOWLER -->
        <div class="mt-5 bg-blue-50 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p class="text-sm text-slate-500">Current Bowler</p>
            <p class="font-bold text-lg mt-1">Singh</p>
          </div>

          <div class="text-right">
            <p class="text-sm text-slate-500">Figures</p>
            <p class="font-bold text-lg mt-1">3.2 - 24 - 2</p>
          </div>
        </div>

      </div>

      <!-- DELIVERY PAD -->
      <div class="grid grid-cols-3 gap-4 mt-5">

        <button class="score-button bg-white rounded-3xl text-2xl font-bold shadow-sm">0</button>
        <button class="score-button bg-white rounded-3xl text-2xl font-bold shadow-sm">1</button>
        <button class="score-button bg-white rounded-3xl text-2xl font-bold shadow-sm">2</button>

        <button class="score-button bg-white rounded-3xl text-2xl font-bold shadow-sm">3</button>
        <button class="score-button bg-blue-600 text-white rounded-3xl text-2xl font-bold shadow-lg shadow-blue-200">4</button>
        <button class="score-button bg-green-600 text-white rounded-3xl text-2xl font-bold shadow-lg shadow-green-200">6</button>

        <button class="score-button bg-red-600 text-white rounded-3xl text-xl font-bold shadow-lg shadow-red-200">W</button>
        <button class="score-button bg-yellow-500 text-white rounded-3xl text-xl font-bold">WD</button>
        <button class="score-button bg-purple-600 text-white rounded-3xl text-xl font-bold">NB</button>

      </div>

      <!-- RECENT BALLS -->
      <div class="glass rounded-3xl p-5 mt-5">
        <div class="flex items-center justify-between mb-4">
          <h4 class="font-bold">Recent Balls</h4>
          <button class="text-sm text-blue-600 font-medium">Full Commentary</button>
        </div>

        <div class="flex gap-2 overflow-x-auto pb-1">
          <div class="w-12 h-12 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold flex-shrink-0">4</div>
          <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center font-bold flex-shrink-0">1</div>
          <div class="w-12 h-12 rounded-full bg-red-600 text-white flex items-center justify-center font-bold flex-shrink-0">W</div>
          <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center font-bold flex-shrink-0">0</div>
          <div class="w-12 h-12 rounded-full bg-green-600 text-white flex items-center justify-center font-bold flex-shrink-0">6</div>
          <div class="w-12 h-12 rounded-full bg-yellow-500 text-white flex items-center justify-center font-bold flex-shrink-0">WD</div>
        </div>
      </div>
    </section>

    <!-- PLAYER SNAPSHOT -->
    <section class="px-5 mt-8 mb-32">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-bold text-xl">Player Insights</h3>
        <button class="text-sm text-blue-600 font-medium">View Squad</button>
      </div>

      <div class="glass rounded-3xl p-5 flex items-center gap-4">

        <div class="w-20 h-20 rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-700 text-white flex items-center justify-center text-2xl font-bold">
          AS
        </div>

        <div class="flex-1">
          <div class="flex items-center justify-between">
            <div>
              <h4 class="font-bold text-lg">Amit Sethi</h4>
              <p class="text-sm text-slate-500">Captain • All Rounder</p>
            </div>

            <button class="bg-slate-100 px-4 py-2 rounded-xl text-sm font-medium">
              Profile
            </button>
          </div>

          <div class="grid grid-cols-3 gap-3 mt-5">
            <div>
              <p class="text-xs text-slate-500">Runs</p>
              <p class="font-bold text-xl mt-1">468</p>
            </div>

            <div>
              <p class="text-xs text-slate-500">Wickets</p>
              <p class="font-bold text-xl mt-1">14</p>
            </div>

            <div>
              <p class="text-xs text-slate-500">SR</p>
              <p class="font-bold text-xl mt-1">142</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- FLOATING ASSISTANT -->
    <button class="fixed bottom-24 right-6 bg-black text-white px-5 py-4 rounded-full shadow-2xl flex items-center gap-3 z-50">
      <span class="text-xl">🤖</span>
      <span class="font-semibold">Ask Assistant</span>
    </button>

    <!-- BOTTOM NAV -->
    <nav class="fixed bottom-0 left-0 right-0 max-w-md mx-auto glass border-t border-white/50 bottom-safe z-40">

      <div class="grid grid-cols-5 py-3">

        <button class="flex flex-col items-center gap-1 text-blue-600">
          <span class="text-xl">🏠</span>
          <span class="text-[11px] font-semibold">Home</span>
        </button>

        <button class="flex flex-col items-center gap-1 text-slate-400">
          <span class="text-xl">🏏</span>
          <span class="text-[11px] font-semibold">Match</span>
        </button>

        <button class="flex flex-col items-center gap-1 text-slate-400">
          <span class="text-xl">📅</span>
          <span class="text-[11px] font-semibold">Fixtures</span>
        </button>

        <button class="flex flex-col items-center gap-1 text-slate-400">
          <span class="text-xl">👥</span>
          <span class="text-[11px] font-semibold">Squad</span>
        </button>

        <button class="flex flex-col items-center gap-1 text-slate-400">
          <span class="text-xl">⚙️</span>
          <span class="text-[11px] font-semibold">More</span>
        </button>

      </div>

    </nav>

  </div>

</body>
</html>
