# Cricket App Subscription & Feature Model

## 1. Product Vision

The goal is to make the cricket app accessible to every cricket player while creating sustainable paid services around advanced team management, historical scorecard ingestion, AI assistance, communication, and administrative support.

**Core principle:** Live cricket scoring and player/club statistics remain free so that the app can build broad adoption and a strong cricket network.

---

## 2. Subscription Tiers

| Feature | Free | Super – $4.99/month | Premium – $100/year |
|---|---|---|---|
| Live match scoring | Free / included | Included | Included |
| Player statistics | Included | Included | Included |
| Club statistics | Included | Included | Included |
| View scorecards | Included | Included | Included |
| Historical scorecard image uploads | 2/month | 5/month | Unlimited |
| Multi-club selection | — | Included | Included |
| Match roster management | — | Included | Included |
| Player availability marking | — | Included | Included |
| Playing XI / team management | — | Included | Included |
| Alerts and player notifications | — | Included | Included |
| Score/sub-score updates to players | — | Included | Included |
| AI assistant | — | Included | Included |
| Historical analysis | Basic | Included | Advanced |
| Club/player analysis | Basic | Included | Advanced |
| AI-assisted historical score extraction | Basic | Included | Advanced |
| Admin support for retro score uploads | — | Basic | Included / priority |
| Cross-club statistics | — | — | Included |
| Match intelligence | — | — | Included |
| Priority support | — | — | Included |

---

## 3. Free Plan – $0

### Purpose
Make the application available to every cricket player and encourage adoption through free scoring and statistics.

### Included

- Unlimited live match scoring
- Player statistics
- Club statistics
- View historical scorecards
- Basic player profile and match history
- **2 historical scorecard image uploads per month**

### Positioning

**For every cricket player**

The Free plan should provide enough value for an individual player to use the application regularly without requiring a subscription.

---

## 4. Super Plan – $4.99/month

### Purpose
Provide active players, captains, and teams with team-management and communication capabilities.

### Included

Everything in Free, plus:

- **5 historical scorecard image uploads per month**
- Multi-club selection
- Match roster management
- Player availability marking
- Playing XI / team management
- Player alerts and notifications
- Score and sub-score updates to players
- AI assistant
- Historical match analysis
- Player and club analysis
- AI-assisted scorecard extraction
- Basic administrative assistance for historical score uploads

### Positioning

**For active players & teams**

Super is intended for players who participate regularly and need more than basic scoring and statistics.

---

## 5. Premium Plan – $100/year

### Purpose
Provide a complete experience for serious players, captains, clubs, and users managing substantial historical cricket data.

### Included

Everything in Super, plus:

- **Unlimited historical scorecard image uploads**
- Advanced AI-assisted scorecard extraction
- Advanced AI analysis
- Cross-club statistics
- Advanced player and club analysis
- Match intelligence
- Advanced historical analysis
- Retro-score upload assistance
- Priority administrative/support assistance
- Expanded AI capabilities

### Pricing

**$100/year**

Equivalent monthly cost when averaged across the year:

**$8.33/month**

### Positioning

**For serious players, captains & clubs**

---

## 6. What Should Remain Free

The following capabilities should remain free because they are fundamental to the cricket experience and help drive adoption:

### Live Scoring

New live match scoring should be available to everyone at no cost.

### Player Statistics

Players should be able to see their own cricket statistics without paying.

### Club Statistics

Basic club statistics should remain accessible to support club participation and engagement.

### Scorecard Viewing

Users should be able to view scorecards and match results without requiring a subscription.

The objective is to avoid putting a paywall around the core cricket experience.

---

## 7. What Should Be Paid

The paid plans should focus on capabilities that provide additional convenience, automation, management, intelligence, or scale.

### Historical Data Import

Uploading old scorecards through images requires extraction, validation, processing, and potentially manual correction. This provides a natural subscription boundary.

### Team & Club Management

Capabilities such as:

- Managing multiple clubs
- Building match rosters
- Tracking availability
- Managing playing XI
- Sending player notifications

are primarily management features and can be reserved for paid users.

### AI Assistance

AI-powered:

- Cricket questions and answers
- Historical analysis
- Player analysis
- Club analysis
- Scorecard extraction
- Match intelligence
- AI Live Scorer Assistant

can be included in the paid experience.

 **Premium should include an agentic AI Live Scorer that listens to the match, interprets ball-by-ball events, sends structured events to your deterministic cricket scoring engine, and updates the live scorecard automatically.**

The important distinction is:

**Free:** Human operates the scoring UI.
**Super:** AI helps with questions, analysis, and team management.
**Premium:** **AI operates the live scoring workflow.**

For example:

> Scorer: “Four.”
> AI → `RUNS: 4` → Scoring Engine → **84/2 → 88/2** → batter +4 → live scorecard updated → spectators notified.

And for:

> “Wide, then two runs.”

AI should generate the appropriate structured events, validate them against the current match state, and let the scoring engine handle all cricket calculations.

This is much closer to the **agentic model** behind Muse, where the AI Scorer Assitant takes an intended action rather than simply responding conversationally. 



### Administrative Assistance

Manual or assisted processing of historical scorecards can be positioned as a premium service, particularly for users with large archives.

---

## 8. Product Positioning

A simple positioning strategy is:

> **Your cricket. Every match. One place.**

Alternative positioning:

> **Score. Track. Play. Connect.**

The central message should be that the application is useful to every player, regardless of whether they pay.

---

## 9. Recommended Pricing Presentation

The pricing page should clearly communicate that live scoring is free.

### Free

**$0**

**For every cricket player**

- Unlimited live scoring
- Player statistics
- Club statistics
- Scorecard history
- 2 historical scorecard uploads/month

### Super

**$4.99/month**

**For active players & teams**

Everything in Free, plus:

- 5 historical scorecard uploads/month
- Multi-club support
- Rosters and availability
- Player alerts
- AI assistant
- Historical and player analysis

### Premium

**$100/year**

**For serious players, captains & clubs**

Everything in Super, plus:

- Unlimited historical uploads
- Advanced AI
- Cross-club statistics
- Match intelligence
- Advanced analysis
- Retro-score assistance
- Priority support

---

## 10. Product Strategy

The subscription model should follow a simple principle:

> **Do not charge users simply to play cricket or see their own cricket history. Charge for managing more cricket, importing more history, automation, communication, and intelligence.**

This allows the application to remain accessible while creating clear reasons for active users, captains, and clubs to upgrade.

---

## 11. Metrics to Monitor

Before permanently locking the subscription economics, monitor:

- Number of free users
- Free-to-paid conversion
- Historical scorecard uploads per user
- Number of live matches scored
- Players per match
- Number of clubs
- Multi-club usage
- Notification usage
- AI assistant usage
- AI/image-processing cost per user
- Administrative support volume
- Super monthly retention
- Premium annual renewal rate

These metrics will help determine whether the current pricing and feature boundaries remain sustainable as usage grows.

---

## 12. Summary

The proposed model is:

**Free**
- Unlimited live scoring
- Player and club statistics
- Scorecard viewing
- 2 historical image uploads/month

**Super – $4.99/month**
- 5 historical image uploads/month
- Team and club management
- Availability and rosters
- Alerts
- AI assistant
- Historical and player/club analysis

**Premium – $100/year**
- Unlimited historical uploads
- Advanced AI
- Advanced analysis
- Cross-club statistics
- Match intelligence
- Retro-score assistance
- Priority support

The overall objective is to keep the core cricket experience free while monetizing advanced management, historical data processing, AI, communication, and administrative capabilities.
