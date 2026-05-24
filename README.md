# Elyon

Deterministic multi-agent CLI workspace for autonomous software engineering.

Elyon orchestrates heterogeneous AI agents in parallel, drives them through a Rust TUI, and reduces token spend by 80%+ using AST-based context trimming via the [ZeroLang](https://github.com/vercel-labs/zerolang) compiler.

## Features

- **Multi-agent TUI** — side-by-side agent panes (tmux-like) with parallel broadcast to all agents. Each agent gets its own provider, status, and interaction history.
- **Token efficiency** — Elyon's ZeroLang compiler strips function bodies, docstrings, and comments from source files before sending them to the LLM. AST skeletons preserve signatures, types, and structure — typically 80-92% fewer tokens (SDR 0.75–0.92).
- **Parallel execution** — `elyon broadcast --providers gemini aider` dispatches the same prompt to every provider concurrently via `asyncio.gather`.
- **Repair loop** — compiler diagnostics feed back into an automated repair cycle: diagnose, repair, verify, repeat (up to N attempts).
- **Deterministic runtime** — Rust sandbox executes agent commands with configurable timeouts, stdout/stderr limits, and policy enforcement.
- **Event tracing** — every agent interaction, AST update, and runtime event is logged to a JSONL event store for full traceability.
- **Provider-agnostic** — any HTTP-based LLM provider works. Configure base URL, model, temperature, and max tokens per agent.

## Quick Start

```bash
# Prerequisites: Python >=3.11, Rust toolchain, ZeroLang binary

# Install Python package
pip install -e .

# Build the Rust runtime (TUI)
cd runtime && cargo build --release --bin elyon-runtime --bin elyon-tui --features tui && cd ..

# Symlink runtime binary
mkdir -p .zero/bin && ln -sf "$(pwd)/runtime/target/release/elyon-tui" .zero/bin/elyon-runtime

# Configure
cp configs/elyon.example.toml elyon.toml

# Launch TUI
elyon
```

## CLI Reference

| Command                                                   | Description                                         |
| --------------------------------------------------------- | --------------------------------------------------- |
| `elyon`                                                   | Launch the TUI (default)                            |
| `elyon shell`                                             | Interactive REPL                                    |
| `elyon tui`                                               | Launch TUI explicitly                               |
| `elyon run --prompt <text>`                               | Send prompt to a single provider                    |
| `elyon broadcast --prompt <text> --providers p1 p2`       | Send prompt to multiple providers in parallel       |
| `elyon compile --zero <file>`                             | Compile a `.zero` file and estimate token savings   |
| `elyon compile --diagnostics <file>`                      | Parse a diagnostics JSON file                       |
| `elyon compile --exec-command <cmd>`                      | Compile & execute a command through the runtime     |
| `elyon repair --diagnostics <file> --attempt <N>`         | Attempt to repair code from diagnostics             |
| `elyon repair --diagnostics <file> --attempt <N> --apply` | Repair and apply the patch                          |
| `elyon doctor`                                            | Check system health and agent detection             |
| `elyon agents`                                            | List detected AI CLI agents                         |
| `elyon providers`                                         | List configured providers                           |
| `elyon project --file <file>`                             | Execute a multi-step project from a JSONL task file |
| `elyon project --file <file> --dry-run`                   | Simulate project execution without side effects     |
| `elyon sandbox --command <cmd>`                           | Run a command through the sandbox policy engine     |
| `elyon trace --trace-id <id>`                             | Replay events for a given trace                     |
| `elyon init --output <path>`                              | Initialize a new Elyon workspace                    |

## TUI Hotkeys

| Key             | Action                         |
| --------------- | ------------------------------ |
| `q` / `Ctrl+X`  | Exit                           |
| `i` / `Enter`   | Enter command mode             |
| `Esc`           | Cancel / return to normal mode |
| `Up` / `k`      | Select previous agent          |
| `Down` / `j`    | Select next agent              |
| `:spawn <name>` | Add a new agent at runtime     |

Commands typed in command mode are broadcast to **all** agents simultaneously.

## Configuration

Elyon uses TOML config files. See [`configs/elyon.example.toml`](configs/elyon.example.toml).

```toml
default_provider = "local_mock"

[providers.local_mock]
name = "local_mock"
base_url = ""
model = "local-model"
default_temperature = 0.0
default_max_tokens = 1024
timeout_seconds = 15.0

[agents.planner]
name = "planner"
role = "planner"
provider = "local_mock"
description = "Plans and decomposes tasks"

[runtime]
command = [".zero/bin/elyon-runtime"]
request_timeout_seconds = 60.0

[compiler]
# Path to ZeroLang binary. Auto-detects from .zero/bin/zero then $PATH.
# zerolang_path = ".zero/bin/zero"
```

Set `ELYON_CONFIG` env var or pass `--config <path>` to point at a config file.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLI (Python)                                       │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐    │
│  │ run      │ │ broadcast│ │ repair            │    │
│  │ ─prompt  │ │ ─providers│ │ ─diagnostics     │    │
│  └──────────┘ └──────────┘ └───────────────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐    │
│  │ project  │ │ compile  │ │ shell / tui       │    │
│  └──────────┘ └──────────┘ └───────────────────┘    │
├─────────────────────────────────────────────────────┤
│  Engine (orchestration/)                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────────┐   │
│  │ providers  │ │ compiler   │ │ event store    │   │
│  │ (HTTP/mock)│ │ (ZeroLang  │ │ (JSONL trace)  │   │
│  │            │ │  AST trim) │ │                │   │
│  └────────────┘ └────────────┘ └────────────────┘   │
├─────────────────────────────────────────────────────┤
│  Runtime (Rust)                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────────┐   │
│  │ executor   │ │ sandbox    │ │ TUI (ratatui)  │   │
│  │ (process)  │ │ (policy)   │ │ (multi-pane)   │   │
│  └────────────┘ └────────────┘ └────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### How Token Efficiency Works

1. Source files (`.py`, `.rs`) are parsed by the ZeroLang compiler into AST skeletons
2. Function bodies, docstrings, comments, and whitespace are stripped
3. Signatures, type annotations, class/struct definitions, and imports are preserved
4. The skeleton (typically 8–25% of original size) is sent to the LLM
5. SDR (Savings-to-Data Ratio) tracks efficiency: `SDR = 1 - Tokens_Transmitted / Tokens_Raw`

### Parallel Agent Broadcast

The TUI and `broadcast` command dispatch the same prompt to all configured agents concurrently. Each agent:

- Maps to its own provider (different model, endpoint, temperature)
- Runs in an independent `asyncio.Task` (Python) or `tokio::spawn` (Rust)
- Reports status (idle → reasoning → idle) and interaction history independently
- Results are collected and displayed per-agent in their respective panes

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type-check
mypy

# Lint
ruff check .

# Build Rust TUI
cargo build --release --bin elyon-tui --features tui -p elyon-runtime
```

## Project Structure

```
elyon/
├── cli/                  # Python CLI (argparse, commands, TUI launcher)
│   ├── main.py           # Entry point, arg parser, dispatch
│   ├── commands/         # Command implementations
│   └── tui.py            # Python TUI stub (delegates to Rust binary)
├── runtime/              # Rust runtime (executor, sandbox, TUI)
│   └── src/bin/elyon-tui.rs   # Multi-pane TUI with ratatui
├── orchestration/        # Engine, agents, project planner
├── providers/            # HTTP provider for LLM APIs
├── compiler/             # ZeroLang integration, AST trimming
├── telemetry/            # SDR metrics, logging
├── repair/               # Diagnostic-driven repair loop
├── state/                # Session state management
├── bindings/             # Language bindings
├── sandbox/              # Command policy engine
├── native/zero-c/        # ZeroLang compiler submodule
├── configs/              # Example configs
├── scripts/              # Utility scripts
└── tests/                # Test suite (86 tests)
```
