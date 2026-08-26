# Contributing to MIA

Thanks for considering a contribution — bug reports, feature requests, and pull requests are all welcome.

## Reporting a bug

Open an [issue](../../issues/new/choose) using the bug report template. Include:
- Your OS version and Python version
- The AI provider you're using (Gemini / OpenAI / Ollama)
- Steps to reproduce, what you expected, and what actually happened
- Relevant output from `Logs/server.log` if it's a backend error (redact anything sensitive first)

## Suggesting a feature

Open an [issue](../../issues/new/choose) using the feature request template. Explain the use case, not just the mechanism — what are you trying to accomplish?

## Making a pull request

1. Fork the repo and create a branch off `main`.
2. Keep the change focused — one feature or fix per PR is easier to review than a bundle of unrelated changes.
3. Follow the existing patterns in the codebase:
   - New agent tools go in `server/plugins/*.py`, registered with the `@tool(...)` decorator (see `server/plugins/system.py` for an example).
   - New skills go under `data/skills/<name>/SKILL.md` with the same frontmatter shape as the existing skills.
   - Frontend changes should reuse the existing CSS tokens in `frontend/css/main.css` rather than introducing new hardcoded colors.
4. Test your change manually against a running instance (there's no automated test suite yet — if you want to add one, that's a very welcome contribution on its own).
5. Open the PR with a clear description of what changed and why.

## Security issues

This app grants full administrative control over a PC to anyone with a valid login token. If you find a security vulnerability (auth bypass, injection, etc.), please **don't** open a public issue — instead reach out to the maintainer directly so it can be fixed before disclosure.

## Code style

- Python: keep functions small and follow the style already used in the file you're editing (docstrings on public functions, type hints where the surrounding code already uses them).
- JS/CSS: no build step — plain vanilla JS/CSS, consistent with the rest of `frontend/`.
- Don't add new dependencies for something a few lines of code can do.
