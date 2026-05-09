# SDEAS Evolution

Self-evolving agent framework for Second Brain systems.

## Branches
- `main` — stable
- `sdeas-evolution-*` — evolution experiments

## Current Evolution
- Branch: `sdeas-evolution-20260509_102138`
- Commits: 5 evolution commits + 1 initial
- Tests: 23/23 passing
- Safety gates: active (4/5 proposals rejected in last run)

## Usage
```bash
PYTHONPATH=src uv run python3 src/hermes_evolve.py --repo . --evolve --max 5 --apply
```
