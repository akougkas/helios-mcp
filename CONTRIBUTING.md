# Contributing to helios-mcp

## Setup

Install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

## Running the test suite

```bash
uv run --frozen pytest
```

## Linting and type checking

```bash
uv run ruff check .
uv run mypy src
```

## Pre-commit hooks

Install the git hooks so ruff and the standard hygiene checks run automatically before each commit:

```bash
uvx pre-commit install
```
