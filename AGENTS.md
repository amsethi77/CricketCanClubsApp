# Instructions for AI coding tools

This file is read by AI assistants (Claude Code, Codex, Copilot, Cursor, Gemini, etc.).

**Before you finish any change, update `README.md`:**
- Add or update the section that describes the feature, page, API or rule you changed.
- Add a dated line to "Change log" at the end of `README.md`.
- Add the user's request, in plain words, to "Prompt And Requirement Log".

Other rules (full list in `README.md` -> "Instructions for AI tools"):
- The iOS and Android apps load these web pages: check your change at phone width (390px) and laptop width.
- Never commit `app/data/*.db*`, `app/data/*_cache.json`, `app/data/.stats_version`, `app/uploads/` or `.env` (Stripe keys).
- Run the app with `python app\main.py` (port 8090) and test the pages you touched before handing over.
- Keep Windows line endings (CRLF) in existing files.
