"""
Cricket AI Prompt Library
Use this file as the central prompt registry for all LLM interactions.
"""

# =========================================================
# 🟢 LLM STATUS INDICATOR
# =========================================================

LLM_STATUS_INDICATOR = """
The Assistant header shows a live status chip with a colored dot and label:

- Solid green: Online
- Blinking green: Thinking
- Blinking red: Connecting
- Solid red: Offline

Use this status chip to reflect the live Ollama endpoint state and the current chat request phase.
"""

# =========================================================
# 🧠 CORE SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are a cricket analytics assistant for a local club management system.

You have access to structured data from:
- matches
- innings
- batting and bowling stats
- player profiles (members)
- team history

Rules:
- Always base answers ONLY on provided data
- Do NOT hallucinate players or scores
- If data is missing, say "insufficient data"
- Normalize player names before matching
- Prefer recent performance (last 5 matches)
- Provide concise but insightful responses
"""

# =========================================================
# 📊 PLAYER ANALYSIS
# =========================================================

PLAYER_STATS = """
Given the following player statistics:

{player_data}

Provide:
1. Total runs
2. Average
3. Strike rate (if balls available)
4. Recent form (last 5 innings)
5. Key strengths

Return in structured bullet format.
"""

COMPARE_PLAYERS = """
Compare the following players:

{player_1_data}
{player_2_data}

Analyze:
- Consistency
- Strike rate
- Performance under pressure
- Contribution to team wins

Recommend who is better for next match and why.
"""

# =========================================================
# 🔮 PLAYER PREDICTIONS
# =========================================================

PREDICT_PLAYER_RUNS = """
Based on the player's past performance:

{player_history}

Predict:
- Expected runs range for next match
- Probability of scoring 30+
- Risk level (low / medium / high)

Factors:
- Recent form
- Opposition strength
- Batting position
"""

BREAKOUT_PLAYERS = """
From the following players dataset:

{team_players_data}

Identify:
- Emerging players
- Underperforming players
- Potential match winners

Explain reasoning using recent performance trends.
"""

# =========================================================
# 🏏 PLAYING XI SELECTION
# =========================================================

SELECT_PLAYING_XI = """
Select the best Playing XI from:

{available_players}

Constraints:
- Balance: batsmen, all-rounders, bowlers
- Prefer in-form players
- Include at least 5 bowling options
- Consider consistency over one-off performance

Output:
- Final XI
- Captain suggestion
- Key players to watch
"""

SELECT_XI_WITH_AVAILABILITY = """
Given:
Available players: {availability_list}
Performance data: {player_stats}

Select the optimal Playing XI considering:
- Availability
- Recent performance
- Team balance

Explain each selection briefly.
"""

# =========================================================
# 📈 MATCH ANALYSIS
# =========================================================

MATCH_ANALYSIS = """
Analyze this match:

{match_json}

Provide:
- Top performers
- Turning point
- Why the team won/lost
- Improvement suggestions
"""

TEAM_ANALYSIS = """
Based on last 10 matches:

{team_history}

Analyze:
- Batting strength
- Bowling effectiveness
- Weak areas

Provide actionable insights.
"""

# =========================================================
# 📊 CLUB INSIGHTS
# =========================================================

CLUB_PERFORMANCE = """
Analyze club performance:

{club_data}

Provide:
- Win/loss ratio
- Top 5 players
- Most consistent performer
- Areas to improve
"""

# =========================================================
# 📉 ANOMALY DETECTION
# =========================================================

ANOMALY_DETECTION = """
From this dataset:

{match_data}

Identify:
- Unusual performances
- Sudden drops in form
- Outliers

Explain possible reasons.
"""

# =========================================================
# 📲 WHATSAPP GENERATION
# =========================================================

WHATSAPP_MATCH_RESULT = """
Generate a WhatsApp message:

Match: {match_data}

Format:
- Short
- Clean
- Emoji friendly

Include:
- Result
- Top performer
- Key highlight
"""

WHATSAPP_PLAYING_XI = """
Generate WhatsApp message:

Playing XI: {players}

Make it:
- Clean
- Engaging
- Club-style tone
"""

# =========================================================
# 🧠 PLAYER MATCHING
# =========================================================

PLAYER_MATCHING = """
Given:
Input name: "{input_name}"
Members list: {members}

Find the best match using:
- Exact match
- Normalized match
- Fuzzy similarity

Return:
- matched_name
- confidence score
"""

# =========================================================
# 🔥 ADVANCED ANALYTICS
# =========================================================

PREDICT_MATCH_WINNER = """
Given:
Team A stats: {team_a}
Team B stats: {team_b}

Predict:
- Winner
- Winning probability
- Key matchup (batsman vs bowler)

Explain reasoning clearly.
"""

# =========================================================
# 🧩 HELPER FUNCTION
# =========================================================

def build_prompt(template: str, **kwargs) -> str:
    """
    Utility to safely format prompts
    """
    return template.format(**kwargs)
