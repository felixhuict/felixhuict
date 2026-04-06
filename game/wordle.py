#!/usr/bin/env python3
"""GitHub Wordle game engine. Processes guesses and updates the README."""

import json
import hashlib
import io
import os
import sys

# Ensure stdout handles Unicode (needed on Windows)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path

GAME_DIR = Path(__file__).parent
ROOT_DIR = GAME_DIR.parent
STATE_FILE = GAME_DIR / "state.json"
WORDS_FILE = GAME_DIR / "words.txt"
README_FILE = ROOT_DIR / "README.md"
LEADERBOARD_FILE = GAME_DIR / "leaderboard.json"


def load_words():
    return [w.strip().upper() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines() if w.strip()]


def get_today_word():
    """Deterministically pick a word based on the date."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    words = load_words()
    seed = int(hashlib.sha256(today.encode()).hexdigest(), 16)
    return words[seed % len(words)], today


def load_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_leaderboard():
    if LEADERBOARD_FILE.exists():
        return json.loads(LEADERBOARD_FILE.read_text(encoding="utf-8"))
    return {}


def save_leaderboard(lb):
    LEADERBOARD_FILE.write_text(json.dumps(lb, indent=2) + "\n", encoding="utf-8")


def score_guess(guess, target):
    """Return list of (letter, status) tuples. Status: 'correct', 'present', 'absent'."""
    result = [None] * 5
    target_chars = list(target)

    # First pass: correct letters
    for i in range(5):
        if guess[i] == target[i]:
            result[i] = (guess[i], "correct")
            target_chars[i] = None

    # Second pass: present/absent
    for i in range(5):
        if result[i] is not None:
            continue
        if guess[i] in target_chars:
            result[i] = (guess[i], "present")
            target_chars[target_chars.index(guess[i])] = None
        else:
            result[i] = (guess[i], "absent")

    return result


def render_guess_row(scored):
    """Render a scored guess as emoji squares and letters."""
    emoji_map = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
    squares = " ".join(emoji_map[s] for _, s in scored)
    letters = " ".join(f"**{l}**" for l, _ in scored)
    return squares, letters


def render_empty_row():
    return "⬜ ⬜ ⬜ ⬜ ⬜", "  .  .  .  .  ."


def render_keyboard(guesses_scored):
    """Render a keyboard showing letter statuses."""
    letter_status = {}
    priority = {"correct": 3, "present": 2, "absent": 1}

    for scored in guesses_scored:
        for letter, status in scored:
            current = letter_status.get(letter, ("unused", 0))
            if priority.get(status, 0) > current[1]:
                letter_status[letter] = (status, priority[status])

    rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    style_map = {"correct": "🟩", "present": "🟨", "absent": "⬛", "unused": "⬜"}

    keyboard_lines = []
    for row in rows:
        line = " ".join(f"{style_map[letter_status.get(c, ('unused', 0))[0]]}`{c}`" for c in row)
        keyboard_lines.append(line)

    return "\n".join(keyboard_lines)


def generate_readme(state):
    """Generate the full README.md content."""
    word_today, today_date = get_today_word()
    guesses = state["guesses"]
    solved = state["solved"]
    max_guesses = state["max_guesses"]

    # Score all guesses
    scored_guesses = []
    for g in guesses:
        scored_guesses.append(score_guess(g["word"], word_today))

    # Build game board
    board_lines = []
    for i in range(max_guesses):
        if i < len(scored_guesses):
            squares, letters = render_guess_row(scored_guesses[i])
            player = guesses[i]["player"]
            board_lines.append(f"| {i+1} | {squares} | {letters} | [@{player}](https://github.com/{player}) |")
        else:
            squares, letters = render_empty_row()
            board_lines.append(f"| {i+1} | {squares} | {letters} | |")

    board = "\n".join(board_lines)

    # Status message
    if solved:
        status = f"🎉 **SOLVED by [@{state['solved_by']}](https://github.com/{state['solved_by']})** in {len(guesses)} guess{'es' if len(guesses) != 1 else ''}! Come back tomorrow for a new word!"
    elif len(guesses) >= max_guesses:
        status = f"💀 **GAME OVER!** The word was **{word_today}**. Better luck tomorrow!"
    else:
        remaining = max_guesses - len(guesses)
        status = f"🔤 **{remaining} guess{'es' if remaining != 1 else ''} remaining** — Submit a PR to play!"

    # Keyboard
    keyboard = render_keyboard(scored_guesses)

    # Leaderboard
    lb = load_leaderboard()
    lb_lines = []
    sorted_players = sorted(lb.items(), key=lambda x: (-x[1]["wins"], x[1].get("total_guesses", 0)))
    for rank, (player, stats) in enumerate(sorted_players[:10], 1):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(rank, f"#{rank}")
        wins = stats["wins"]
        avg = stats.get("total_guesses", 0) / max(wins, 1)
        lb_lines.append(f"| {medal} | [@{player}](https://github.com/{player}) | {wins} | {avg:.1f} |")

    leaderboard_table = "\n".join(lb_lines) if lb_lines else "| | *No winners yet — be the first!* | | |"

    # Share pattern (for solved games)
    share_section = ""
    if solved or len(guesses) >= max_guesses:
        pattern_lines = []
        for scored in scored_guesses:
            emoji_map = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
            pattern_lines.append("".join(emoji_map[s] for _, s in scored))
        result_num = len(guesses) if solved else "X"
        share_text = f"GitHub Wordle #{state['day']} {result_num}/{max_guesses}\\n" + "\\n".join(pattern_lines)
        share_section = f"""
<details>
<summary>📋 Share your result</summary>

```
GitHub Wordle #{state['day']} {result_num}/{max_guesses}

{chr(10).join(pattern_lines)}
```

</details>
"""

    readme = f"""<div align="center">

# 🟩 GitHub Wordle

### A collaborative Wordle game played through Issue Comments!

**Day #{state['day']}** · {today_date}

---

{status}

</div>

## 🎮 Today's Board

| # | Result | Letters | Player |
|---|--------|---------|--------|
{board}

{share_section}

<details>
<summary>⌨️ Keyboard</summary>

<div align="center">

{keyboard}

</div>

</details>

---

## 🏆 Leaderboard

| Rank | Player | Wins | Avg Guesses |
|------|--------|------|-------------|
{leaderboard_table}

---

## 🕹️ How to Play

1. **Go to the [Game Issue](../../issues)** (look for the pinned Wordle issue)
2. **Post a comment** with your guess:
   ```
   guess: YOURWORD
   ```
   For example: `guess: CRANE`
3. The GitHub Action will **process your guess** and reply with your result
4. The **game board** in the README will be updated automatically

### 📜 Rules

- Words must be **exactly 5 letters**
- Words must be in the **valid word list**
- Players can guess **multiple times per day**
- The game resets **every 24 hours at midnight UTC**
- **6 total guesses** shared across all players — work together!
- 🟩 = Correct letter, correct position
- 🟨 = Correct letter, wrong position
- ⬛ = Letter not in the word

### 🤝 Strategy Tips

- Check the **keyboard** to see which letters have been eliminated
- Build on previous guesses — don't waste letters already marked ⬛
- Coordinate in the [Discussions](../../discussions) tab!

---

<div align="center">

**New word every day at 🕛 00:00 UTC**

Built with 💚 by the community · Powered by GitHub Actions

</div>
"""
    return readme


def process_guess(word, player):
    """Process a guess and return (success, message)."""
    word = word.upper().strip()
    state = load_state()
    target, today = get_today_word()

    # Reset if new day
    if state["date"] != today:
        day_num = state.get("day", 0) + 1
        state = {
            "word": "",
            "day": day_num,
            "guesses": [],
            "solved": False,
            "solved_by": None,
            "date": today,
            "max_guesses": 6,
        }

    # Validation
    if state["solved"]:
        return False, f"🎉 Today's word has already been solved by @{state['solved_by']}! Come back tomorrow."

    if len(state["guesses"]) >= state["max_guesses"]:
        return False, "💀 No guesses remaining today! The game is over. Come back tomorrow."

    if len(word) != 5:
        return False, f"❌ `{word}` is not 5 letters. Please guess a 5-letter word."

    if not word.isalpha():
        return False, f"❌ `{word}` contains non-letter characters. Only A-Z allowed."

    valid_words = load_words()
    if word not in valid_words:
        return False, f"❌ `{word}` is not in the word list. Try a different word."

    # Score the guess
    scored = score_guess(word, target)
    emoji_map = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
    result_emojis = " ".join(emoji_map[s] for _, s in scored)
    result_letters = " ".join(f"**{l}**" for l, _ in scored)

    # Record guess
    state["guesses"].append({"word": word, "player": player, "time": datetime.now(timezone.utc).isoformat()})

    # Check win
    is_correct = all(s == "correct" for _, s in scored)
    if is_correct:
        state["solved"] = True
        state["solved_by"] = player

        # Update leaderboard
        lb = load_leaderboard()
        if player not in lb:
            lb[player] = {"wins": 0, "total_guesses": 0, "games": []}
        lb[player]["wins"] += 1
        lb[player]["total_guesses"] += len(state["guesses"])
        lb[player]["games"].append({"day": state["day"], "guesses": len(state["guesses"]), "date": today})
        save_leaderboard(lb)

    save_state(state)

    # Generate response
    guess_num = len(state["guesses"])
    if is_correct:
        msg = f"""## 🎉 Correct!

| Result | Letters |
|--------|---------|
| {result_emojis} | {result_letters} |

**@{player}** solved today's Wordle in **{guess_num} guess{'es' if guess_num != 1 else ''}**! 🏆

The word was **{target}**!"""
    elif guess_num >= state["max_guesses"]:
        msg = f"""## 💀 Game Over!

| Result | Letters |
|--------|---------|
| {result_emojis} | {result_letters} |

No guesses remaining. The word was **{target}**.

Better luck tomorrow!"""
    else:
        remaining = state["max_guesses"] - guess_num
        msg = f"""## Guess #{guess_num} by @{player}

| Result | Letters |
|--------|---------|
| {result_emojis} | {result_letters} |

**{remaining} guess{'es' if remaining != 1 else ''} remaining** — who's next?"""

    # Update README
    readme_content = generate_readme(state)
    README_FILE.write_text(readme_content, encoding="utf-8")

    return True, msg


def reset_daily():
    """Reset the game for a new day."""
    target, today = get_today_word()
    state = load_state()

    if state["date"] == today:
        print("Already reset for today.")
        return

    day_num = state.get("day", 0) + 1
    new_state = {
        "word": "",
        "day": day_num,
        "guesses": [],
        "solved": False,
        "solved_by": None,
        "date": today,
        "max_guesses": 6,
    }
    save_state(new_state)
    readme_content = generate_readme(new_state)
    README_FILE.write_text(readme_content, encoding="utf-8")
    print(f"Reset for day #{day_num} ({today})")


def init_game():
    """Initialize the game for the first time."""
    target, today = get_today_word()
    state = {
        "word": "",
        "day": 1,
        "guesses": [],
        "solved": False,
        "solved_by": None,
        "date": today,
        "max_guesses": 6,
    }
    save_state(state)
    readme_content = generate_readme(state)
    README_FILE.write_text(readme_content, encoding="utf-8")
    print(f"Initialized game for day #1 ({today})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: wordle.py [init|reset|guess <word> <player>]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        init_game()
    elif command == "reset":
        reset_daily()
    elif command == "guess":
        if len(sys.argv) < 4:
            print("Usage: wordle.py guess <word> <player>")
            sys.exit(1)
        word = sys.argv[2]
        player = sys.argv[3]
        success, message = process_guess(word, player)
        print(message)
        # Write message to file for GitHub Actions
        msg_file = GAME_DIR / "last_result.md"
        msg_file.write_text(message, encoding="utf-8")
        if not success:
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
