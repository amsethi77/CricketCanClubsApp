READMEScoring.md

To build a production-ready online cricket scorecard website or app, you need a solid database structure, clear backend business logic, and an intuitive user interface.
Here is the exhaustive blueprint covering everything from database schemas to frontend components.
------------------------------
## 1. Database Schema Design (JSON/NoSQL or Relational)
Your application needs to store data across four relational entities: Matches, Innings, Player Performances (Batting), and Player Performances (Bowling).
## A. Match Metadata Schema

{
  "match_id": "M78901",
  "tournament_id": "IPL-2026",
  "match_type": "T20", 
  "status": "LIVE",
  "team_a": { "id": "T1", "name": "Mumbai Indians", "short_name": "MI" },
  "team_b": { "id": "T2", "name": "Chennai Super Kings", "short_name": "CSK" },
  "toss": { "won_by": "T1", "decision": "BAT" },
  "current_innings_no": 1,
  "winner": null
}

## B. Innings State Schema (Live State)

{
  "innings_id": "INN-01",
  "match_id": "M78901",
  "innings_order": 1,
  "batting_team_id": "T1",
  "bowling_team_id": "T2",
  "total_runs": 84,
  "wickets": 2,
  "total_legal_balls": 58, 
  "target": null,
  "extras": { "wides": 4, "no_balls": 1, "byes": 0, "leg_byes": 2, "total": 7 },
  "current_striker_id": "P-101",
  "current_non_striker_id": "P-102",
  "current_bowler_id": "P-201",
  "this_over_balls": ["1", "4", "Wd", "0", "W", "2"] 
}

## C. Player Live Performance Schema

{
  "batting_scores": [
    {
      "player_id": "P-101",
      "name": "R. Sharma",
      "status": "BATTING", 
      "runs": 45,
      "balls_faced": 32,
      "fours": 5,
      "sixes": 2,
      "dismissal_text": ""
    }
  ],
  "bowling_scores": [
    {
      "player_id": "P-201",
      "name": "R. Jadeja",
      "overs_bowled_balls": 16, 
      "maidens": 0,
      "runs_conceded": 22,
      "wickets": 1
    }
  ]
}

------------------------------
## 2. Core Mathematical Logic & Formulas
You must write backend functions or database triggers to compute these variables continuously.

* Displaying Overs:
$$\text{Overs UI} = \lfloor \text{Total Legal Balls} / 6 \rfloor + \left( (\text{Total Legal Balls} \pmod 6) \times 0.1 \right)$$ 
Example: 58 legal balls $\rightarrow \lfloor 58/6 \rfloor = 9$ and $58 \pmod 6 = 4 \rightarrow \mathbf{9.4\ overs}$.
* Current Run Rate (CRR):
$$\text{CRR} = \frac{\text{Total Runs}}{\text{Total Legal Balls}} \times 6$$ 
* Required Run Rate (RRR) — 2nd Innings Only:
$$\text{RRR} = \frac{\text{Target} - \text{Current Runs}}{(\text{Max Match Balls} - \text{Total Legal Balls Bowled})} \times 6$$ 
* Batter Strike Rate (SR):
$$\text{SR} = \left( \frac{\text{Runs Scored}}{\text{Balls Faced}} \right) \times 100$$ 
* Bowler Economy Rate (Econ):
$$\text{Econ} = \frac{\text{Runs Conceded}}{\text{Total Legal Balls Bowled}} \times 6$$ 

------------------------------
## 3. State Management & Trigger Logic (The Scorer Panel)
When the match official clicks a button on the scorer panel, your state machine must execute precise adjustments to player and team objects.
## Event: "Wide Ball"

   1. team_total_runs = team_total_runs + 1
   2. team_extras_wides = team_extras_wides + 1
   3. bowler_runs_conceded = bowler_runs_conceded + 1
   4. Do not increment team_total_legal_balls, batter_balls_faced, or bowler_legal_balls.
   5. Append "Wd" to the this_over_balls array.

## Event: "No-Ball + 4 Hit by Batter"

   1. team_total_runs = team_total_runs + 5 (1 penalty + 4 boundary runs)
   2. team_extras_no_balls = team_extras_no_balls + 1
   3. batter_runs = batter_runs + 4
   4. batter_balls_faced = batter_balls_faced + 1
   5. bowler_runs_conceded = bowler_runs_conceded + 5
   6. Do not increment team_total_legal_balls or bowler_legal_balls.
   7. Append "4NB" to the this_over_balls array.

## Event: "Byes / Leg-Byes (e.g., 2 runs)"

   1. team_total_runs = team_total_runs + 2
   2. team_extras_byes (or leg_byes) = team_extras_byes + 2
   3. team_total_legal_balls = team_total_legal_balls + 1
   4. batter_balls_faced = batter_balls_faced + 1
   5. bowler_legal_balls = bowler_legal_balls + 1
   6. Do not add runs to batter_runs or bowler_runs_conceded.

## Automatic State Changes:

* Strike Rotation (Odd Runs): If runs hit off the bat = 1 or 3, swap the values of current_striker_id and current_non_striker_id.
* Over Completion: When (Total Legal Balls % 6) == 0:
* Swap current_striker_id and current_non_striker_id (strike rotates at the end of an over).
   * Check if bowler_runs_conceded in that block of 6 balls was 0. If yes, increment bowler_maidens by 1.
   * Clear the this_over_balls array for the next over.
   * Lock the current bowler out so they cannot be selected for the immediate next over.

------------------------------
## 4. Frontend Component Architecture
If you are using a component-driven framework (like React, Vue, or Flutter), structure your view into these isolated UI modules:

   1. <InningsSummaryHeader />
   * Displays: "MI 184/3 (18.2)"
      * Displays CRR and RRR side-by-side using high-contrast typography.
   2. <LivePartnershipBar />
   * Fetches the current tracking data of the two active batters.
      * Displays: "Partnership: 52 (34) | Last Wicket: R. Sharma 12 (8)"
   3. <BattingCardTable />
   * A responsive table component.
      * Columns: Batter Name, Dismissal Text (grayed out if out), R, B, 4s, 6s, SR.
      * Apply a CSS class to highlight active batters with a subtle green left border or a bat emoji ($\mathbf{\ast}$ or 🏏).
   4. <BowlingCardTable />
   * Columns: Bowler Name, O, M, R, W, Econ.
   5. <TimelineOverFeed />
   * Maps over the this_over_balls array.
      * Use color-coded badges for visual clarity:
      * Dot (0) → Light gray circle.
         * Boundary (4 or 6) → Bold green or purple square.
         * Wicket (W) → Bright red circle.
      
------------------------------
## 5. Real-Time Sync Strategy
A scorecard is a highly dynamic component. To prevent users from needing to refresh the page constantly, implement one of these two real-time patterns:

* WebSockets (Recommended): Establish a persistent connection between the client app and your server (e.g., using Socket.io or FastAPI WebSockets). Whenever the scorer enters a ball, broadcast a light payload containing the updated match state to all connected clients.
* Server-Sent Events (SSE): Ideal if data only flows one way (from server to user). It uses less overhead than WebSockets and works natively over HTTP.

If you want to start writing code, let me know which programming language or web framework you are planning to use, and I can give you a starter boilerplate code for the scoring calculations!

from dataclasses import dataclass, field
from typing import List, Optional, Dict

# ==========================================
# 1. DATA MODELS
# ==========================================

@dataclass
class BatterStats:
    player_id: str
    name: str
    status: str = "DID_NOT_BAT"  # BATTING, OUT, DID_NOT_BAT
    runs: int = 0
    balls_faced: int = 0
    fours: int = 0
    sixes: int = 0
    dismissal_text: str = ""

    @property
    def strike_rate(self) -> float:
        if self.balls_faced == 0:
            return 0.0
        return round((self.runs / self.balls_faced) * 100, 2)


@dataclass
class BowlerStats:
    player_id: str
    name: str
    legal_balls_bowled: int = 0
    maidens: int = 0
    runs_conceded: int = 0
    wickets: int = 0
    
    # Internal tracker to calculate maidens per over
    runs_in_current_over: int = 0 
    legal_balls_in_current_over: int = 0

    @property
    def overs_display(self) -> str:
        overs = self.legal_balls_bowled // 6
        balls = self.legal_balls_bowled % 6
        return f"{overs}.{balls}"

    @property
    def economy_rate(self) -> float:
        if self.legal_balls_bowled == 0:
            return 0.0
        return round((self.runs_conceded / (self.legal_balls_bowled / 6)), 2)


@dataclass
class ExtrasCounter:
    wides: int = 0
    no_balls: int = 0
    byes: int = 0
    leg_byes: int = 0

    @property
    def total(self) -> int:
        return self.wides + self.no_balls + self.byes + self.leg_byes


@dataclass
class InningsState:
    match_id: str
    batting_team: str
    bowling_team: str
    max_overs: int
    
    total_runs: int = 0
    wickets: int = 0
    total_legal_balls: int = 0
    target: Optional[int] = None
    
    extras: ExtrasCounter = field(default_factory=ExtrasCounter)
    this_over_timeline: List[str] = field(default_factory=list)
    
    striker_id: Optional[str] = None
    non_striker_id: Optional[str] = None
    current_bowler_id: Optional[str] = None
    previous_bowler_id: Optional[str] = None
    
    batting_lineup: Dict[str, BatterStats] = field(default_factory=dict)
    bowling_lineup: Dict[str, BowlerStats] = field(default_factory=dict)

    @property
    def overs_display(self) -> str:
        overs = self.total_legal_balls // 6
        balls = self.total_legal_balls % 6
        return f"{overs}.{balls}"

    @property
    def current_run_rate(self) -> float:
        if self.total_legal_balls == 0:
            return 0.0
        return round((self.total_runs / (self.total_legal_balls / 6)), 2)

    @property
    def required_run_rate(self) -> float:
        if not self.target:
            return 0.0
        balls_remaining = (self.max_overs * 6) - self.total_legal_balls
        runs_needed = self.target - self.total_runs
        if balls_remaining <= 0 or runs_needed <= 0:
            return 0.0
        return round((runs_needed / (balls_remaining / 6)), 2)


# ==========================================
# 2. STATE LOGIC ENGINE
# ==========================================

class CricketScoringEngine:
    def __init__(self, innings: InningsState):
        self.state = innings

    def _rotate_strike(self):
        """Swaps the active striker and non-striker positions."""
        self.state.striker_id, self.state.non_striker_id = (
            self.state.non_striker_id,
            self.state.striker_id,
        )

    def _handle_over_completion(self, bowler: BowlerStats):
        """Manages routines when an over ends (6 legal balls)."""
        # Check and award maiden over status
        if bowler.runs_in_current_over == 0 and bowler.legal_balls_in_current_over == 6:
            bowler.maidens += 1
            
        # Reset current over trackers for the bowler
        bowler.runs_in_current_over = 0
        bowler.legal_balls_in_current_over = 0
        
        # Lock bowler from consecutive overs
        self.state.previous_bowler_id = self.state.current_bowler_id
        self.state.current_bowler_id = None
        
        # Clear visual timeline for the new over
        self.state.this_over_timeline.clear()
        
        # End of over strike rotation rule
        self._rotate_strike()

    def record_ball_event(self, event_type: str, runs_off_bat: int = 0, dismissal_type: Optional[str] = None, next_batter_id: Optional[str] = None):
        """
        Executes core state changes for any ball event.
        Valid event_types: 'NORMAL', 'WIDE', 'NO_BALL', 'BYE', 'LEG_BYE', 'WICKET'
        """
        striker = self.state.batting_lineup.get(self.state.striker_id)
        bowler = self.state.bowling_lineup.get(self.state.current_bowler_id)
        
        if not striker or not bowler:
            raise ValueError("Striker or Bowler context missing from live states.")

        # --- A. EVENT EVALUATION LOOPS ---
        
        if event_type == 'NORMAL':
            self.state.total_runs += runs_off_bat
            self.state.total_legal_balls += 1
            
            striker.runs += runs_off_bat
            striker.balls_faced += 1
            if runs_off_bat == 4: striker.fours += 1
            if runs_off_bat == 6: striker.sixes += 1
            
            bowler.runs_conceded += runs_off_bat
            bowler.runs_in_current_over += runs_off_bat
            bowler.legal_balls_bowled += 1
            bowler.legal_balls_in_current_over += 1
            
            self.state.this_over_timeline.append(str(runs_off_bat))
            if runs_off_bat % 2 != 0:
                self._rotate_strike()

        elif event_type == 'WIDE':
            # Wides add 1 run to extras, penalty to bowler, legal balls do not advance
            wide_runs = 1 + runs_off_bat
            self.state.total_runs += wide_runs
            self.state.extras.wides += wide_runs
            
            bowler.runs_conceded += wide_runs
            bowler.runs_in_current_over += wide_runs
            
            timeline_str = f"Wd" if runs_off_bat == 0 else f"{runs_off_bat}Wd"
            self.state.this_over_timeline.append(timeline_str)
            if runs_off_bat % 2 != 0:
                self._rotate_strike()

        elif event_type == 'NO_BALL':
            # No-Ball adds 1 penalty + whatever the batter scores off it
            self.state.total_runs += (1 + runs_off_bat)
            self.state.extras.no_balls += 1
            
            striker.runs += runs_off_bat
            striker.balls_faced += 1  # No-Balls count as faced by batter
            if runs_off_bat == 4: striker.fours += 1
            if runs_off_bat == 6: striker.sixes += 1
            
            bowler.runs_conceded += (1 + runs_off_bat)
            bowler.runs_in_current_over += (1 + runs_off_bat)
            
            timeline_str = f"NB" if runs_off_bat == 0 else f"{runs_off_bat}NB"
            self.state.this_over_timeline.append(timeline_str)
            if runs_off_bat % 2 != 0:
                self._rotate_strike()

        elif event_type in ['BYE', 'LEG_BYE']:
            self.state.total_runs += runs_off_bat
            self.state.total_legal_balls += 1
            
            if event_type == 'BYE': self.state.extras.byes += runs_off_bat
            else: self.state.extras.leg_byes += runs_off_bat
                
            striker.balls_faced += 1
            # Bowlers do not concede runs for Byes/Leg-byes
            bowler.legal_balls_bowled += 1
            bowler.legal_balls_in_current_over += 1
            
            ext_suffix = "B" if event_type == 'BYE' else "LB"
            self.state.this_over_timeline.append(f"{runs_off_bat}{ext_suffix}")
            if runs_off_bat % 2 != 0:
                self._rotate_strike()

        elif event_type == 'WICKET':
            self.state.wickets += 1
            self.state.total_legal_balls += 1
            
            striker.balls_faced += 1
            striker.status = "OUT"
            striker.dismissal_text = f"b {bowler.name}" if not dismissal_type else dismissal_type
            
            bowler.legal_balls_bowled += 1
            bowler.legal_balls_in_current_over += 1
            
            # Bowler only gets credit if dismissal is not a Run Out
            if dismissal_type != "Run Out":
                bowler.wickets += 1
                
            self.state.this_over_timeline.append("W")
            
            # Bring in new batter immediately
            if next_batter_id and self.state.wickets < 10:
                self.state.striker_id = next_batter_id
                self.state.batting_lineup[next_batter_id].status = "BATTING"
            else:
                self.state.striker_id = None # Innings Over / All Out

        # --- B. OVER COMPLETION HOOK ---
        if bowler.legal_balls_in_current_over == 6:
            self._handle_over_completion(bowler)


# ==========================================
# 3. TEST IMPLEMENTATION EXECUTION
# ==========================================

# Mocking initial game data setup
innings = InningsState(match_id="M01", batting_team="Team A", bowling_team="Team B", max_overs=20)

# Register Players
innings.batting_lineup = {
    "P1": BatterStats(player_id="P1", name="V. Kohli", status="BATTING"),
    "P2": BatterStats(player_id="P2", name="R. Sharma", status="BATTING"),
    "P3": BatterStats(player_id="P3", name="S. Gill")
}
innings.bowling_lineup = {
    "B1": BowlerStats(player_id="B1", name="J. Bumrah")
}

# Set Live States
innings.striker_id = "P1"
innings.non_striker_id = "P2"
innings.current_bowler_id = "B1"

# Initialize our State Machine Engine
engine = CricketScoringEngine(innings)

# Simulate 1 legal complete over with specific variants
engine.record_ball_event('NORMAL', runs_off_bat=1)  # Ball 1 -> P1 gets 1 run, strike rotates
engine.record_ball_event('NORMAL', runs_off_bat=4)  # Ball 2 -> P2 hits a 4
engine.record_ball_event('WIDE', runs_off_bat=0)    # Wide   -> Extra run, doesn't increment over ball


engine.record_ball_event('NORMAL', runs_off_bat=0)  # Ball 3 -> Dot ballengine.record_ball_event('WICKET', dismissal_type="Bowled", next_batter_id="P3") # Ball 4 -> P2 is out! P3 entersengine.record_ball_event('BYE', runs_off_bat=2)     # Ball 5 -> 2 byes takenengine.record_ball_event('NORMAL', runs_off_bat=1)  # Ball 6 -> Over completePrint Results out directly to standard viewprint(f"Score: {innings.total_runs}/{innings.wickets} in {innings.overs_display} Overs")print(f"Extras Breakdown: {innings.extras}")print(f"Current Over Feed: {innings.this_over_timeline}")print(f"Batter 1 ({innings.batting_lineup['P1'].name}): {innings.batting_lineup['P1'].runs} Runs off {innings.batting_lineup['P1'].balls_faced} balls (SR: {innings.batting_lineup['P1'].strike_rate})")print(f"Bowler ({innings.bowling_lineup['B1'].name}): {innings.bowling_lineup['B1'].overs_display} Overs, {innings.bowling_lineup['B1'].wickets} Wkt, {innings.bowling_lineup['B1'].runs_conceded} Runs Conceded (Econ: {innings.bowling_lineup['B1'].economy_rate})")
### Key Python Logic Implementations

*   **`@dataclass` properties:** Python properties automatically handle real-time calculation fields like `strike_rate`, `economy_rate`, and `required_run_rate`. They consume zero processing storage and return values on access.
*   **Integer Conversion for Overs:** To completely isolate floating-point rounding bugs (e.g., `0.1 + 0.2 != 0.3` in standard floats), overs are stored as pure integer ball units (`total_legal_balls`). Floor division `// 6` extraction logic is applied solely when displaying output to the UI string.
*   **Encapsulation of States:** The `CricketScoringEngine` cleanly intercepts any input event, parses dependencies like strike rotation, and processes accurate adjustments to individual components synchronously.

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Live Scoring</title>

  <script src="https://cdn.tailwindcss.com"></script>

  <style>
    .btn { @apply p-4 rounded-xl text-lg font-semibold shadow; }
    .btn-run { @apply bg-green-500 text-white; }
    .btn-extra { @apply bg-orange-500 text-white; }
    .btn-wicket { @apply bg-red-600 text-white; }
    .btn-action { @apply bg-gray-700 text-white; }
  </style>
</head>

<body class="bg-gray-100 text-gray-900">

<div class="max-w-md mx-auto p-3 space-y-3">

  <!-- HEADER -->
  <div class="bg-black text-white p-4 rounded-xl shadow">
    <div class="flex justify-between items-center">
      <h1 class="text-xl font-bold">Heartlake CC</h1>
      <span class="text-sm">LIVE</span>
    </div>

    <div class="text-3xl font-bold mt-2" id="score">
      0/0
    </div>

    <div class="text-sm">
      Overs: <span id="overs">0.0</span> |
      CRR: <span id="crr">0.0</span>
    </div>
  </div>

  <!-- BATTERS -->
  <div class="bg-white p-3 rounded-xl shadow">
    <div class="flex justify-between">
      <div>
        🏏 <span id="striker">Rohit</span>
        <div class="text-sm text-gray-500" id="strikerStats">0 (0)</div>
      </div>
      <div>
        <span id="nonStriker">Gill</span>
        <div class="text-sm text-gray-500" id="nonStrikerStats">0 (0)</div>
      </div>
    </div>
  </div>

  <!-- BOWLER -->
  <div class="bg-white p-3 rounded-xl shadow">
    Bowler: <span id="bowler">Bumrah</span>
    <div class="text-sm text-gray-500" id="bowlerStats">0-0-0-0</div>
  </div>

  <!-- OVER TIMELINE -->
  <div class="bg-white p-3 rounded-xl shadow">
    <div class="flex space-x-2" id="timeline"></div>
  </div>

  <!-- RUN BUTTONS -->
  <div class="grid grid-cols-6 gap-2">
    <button class="btn btn-run" onclick="run(0)">0</button>
    <button class="btn btn-run" onclick="run(1)">1</button>
    <button class="btn btn-run" onclick="run(2)">2</button>
    <button class="btn btn-run" onclick="run(3)">3</button>
    <button class="btn btn-run" onclick="run(4)">4</button>
    <button class="btn btn-run" onclick="run(6)">6</button>
  </div>

  <!-- EXTRAS -->
  <div class="grid grid-cols-5 gap-2">
    <button class="btn btn-extra" onclick="wide()">WD</button>
    <button class="btn btn-extra" onclick="noBall()">NB</button>
    <button class="btn btn-extra" onclick="bye()">BYE</button>
    <button class="btn btn-extra" onclick="legBye()">LB</button>
    <button class="btn btn-wicket" onclick="wicket()">W</button>
  </div>

  <!-- ACTIONS -->
  <div class="grid grid-cols-2 gap-2">
    <button class="btn btn-action" onclick="undo()">UNDO</button>
    <button class="btn btn-action" onclick="changeStrike()">SWAP</button>
  </div>

</div>

<script>
let state = {
  runs: 0,
  wickets: 0,
  balls: 0,
  striker: { runs: 0, balls: 0 },
  nonStriker: { runs: 0, balls: 0 },
  bowler: { runs: 0, balls: 0 },
  timeline: []
};

// ---------- CORE UPDATE ----------
function updateUI() {
  document.getElementById("score").innerText = `${state.runs}/${state.wickets}`;

  let overs = Math.floor(state.balls / 6) + "." + (state.balls % 6);
  document.getElementById("overs").innerText = overs;

  let crr = state.balls ? ((state.runs / state.balls) * 6).toFixed(2) : 0;
  document.getElementById("crr").innerText = crr;

  document.getElementById("strikerStats").innerText =
    `${state.striker.runs} (${state.striker.balls})`;

  document.getElementById("nonStrikerStats").innerText =
    `${state.nonStriker.runs} (${state.nonStriker.balls})`;

  document.getElementById("bowlerStats").innerText =
    `${Math.floor(state.bowler.balls/6)}-${state.bowler.runs}-${state.wickets}`;

  renderTimeline();
}

// ---------- TIMELINE ----------
function renderTimeline() {
  let el = document.getElementById("timeline");
  el.innerHTML = "";
  state.timeline.slice(-6).forEach(ball => {
    let div = document.createElement("div");
    div.className = "w-8 h-8 flex items-center justify-center rounded-full text-white";

    if (ball === "W") div.classList.add("bg-red-600");
    else if (ball === "4" || ball === "6") div.classList.add("bg-green-500");
    else if (ball.includes("Wd") || ball.includes("NB")) div.classList.add("bg-orange-500");
    else div.classList.add("bg-gray-400");

    div.innerText = ball;
    el.appendChild(div);
  });
}

// ---------- EVENTS ----------
function run(r) {
  state.runs += r;
  state.balls++;

  state.striker.runs += r;
  state.striker.balls++;

  state.bowler.runs += r;
  state.bowler.balls++;

  state.timeline.push(String(r));

  if (r % 2 === 1) swap();

  checkOver();
  updateUI();
}

function wide() {
  state.runs += 1;
  state.bowler.runs += 1;
  state.timeline.push("Wd");
  updateUI();
}

function noBall() {
  state.runs += 1;
  state.bowler.runs += 1;
  state.timeline.push("NB");
  updateUI();
}

function bye() {
  state.runs += 1;
  state.balls++;
  state.striker.balls++;
  state.bowler.balls++;
  state.timeline.push("B");
  updateUI();
}

function legBye() {
  state.runs += 1;
  state.balls++;
  state.striker.balls++;
  state.bowler.balls++;
  state.timeline.push("LB");
  updateUI();
}

function wicket() {
  state.wickets++;
  state.balls++;
  state.striker.balls++;
  state.bowler.balls++;
  state.timeline.push("W");
  updateUI();
}

// ---------- HELPERS ----------
function swap() {
  let temp = state.striker;
  state.striker = state.nonStriker;
  state.nonStriker = temp;
}

function changeStrike() {
  swap();
  updateUI();
}

function undo() {
  // basic undo (can enhance)
  location.reload();
}

function checkOver() {
  if (state.balls % 6 === 0) {
    swap();
  }
}

// init
updateUI();

</script>

</body>
</html>