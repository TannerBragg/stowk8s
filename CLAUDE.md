# CLAUDE.md

This file guides Claude Code when working with this Python CLI for Helm chart and image dependencies.

## Development Commands
- Run: `python -m stowk8s` or `stowk8s` (after `pip install -e .`)
- Test: `pytest tests/`
- Lint: `ruff check src/`

The CLI (typer) has two groups: `helm` (chart deps) and `image` (list dependencies). Image discovery uses strategy pattern (`helm-bsi` and `helm-template`) via `StrategyManager` in `stowk8s/strategies`.

Key modules:
- `stowk8s/cli.py`: CLI entry
- `stowk8s/commands/helm.py`: Helm commands
- `stowk8s/commands/image.py`: Image commands
- `stowk8s/strategies/helm_bsi.py`: Helm-BSI strategy
- `stowk8s/strategies/base.py`: Base types
- `stowk8s/strategies/helm_template.py`: Template strategy

Helm requires the `helm` binary on PATH.

## Development Guidelines
- Use typer and rich.
- Enforce type safety with mypy.
- Separate CLI from core logic.
- Handle errors with user-friendly exceptions.
- Follow the parallel development workflow (command logic → validation → execution → formatting → testing → integration → verification).

## Context Optimization
- Each agent should target a single module/service.
- Strip unused imports/comments when reading files.
- Keep context focused on the current command.
- When possible, use agents for multi-file analysis or complex tasks, delegating work to specialized agents rather than manually reading and editing files.