# Elyon

![Elyon Logo](assets/Logo.png)

Deterministic multi-agent CLI workspace for autonomous software engineering.

Elyon orchestrates heterogeneous AI agents in parallel, drives them through a Rust TUI, and provides a structured environment for autonomous coding tasks with intelligent context management, provider routing, and security hardening.

## Purpose

Elyon is a framework for **deterministic, multi-agent software engineering**. It dispatches tasks to AI agents through a structured pipeline that optimizes token usage, manages session context, routes requests to the best provider, and enforces security policies — all while maintaining full traceability through an event store.

## What It Can Do

| Capability | Description |
|------------|-------------|
| **Multi-agent orchestration** | Run multiple AI agents (aider, claude, opencode, etc.) side-by-side with independent providers and configurations |
| **Parallel prompt dispatch** | `elyon broadcast` sends the same prompt to every provider concurrently |
| **Repair loop** | Compiler diagnostics feed into an automated diagnose → repair → verify cycle |
| **Token optimization** | Prompt minification, prefix caching, and context diffing reduce LLM costs by up to 77% |
| **Session memory** | Long-running sessions preserved via extractive summarization (3-tier: working → summarized → meta) |
| **Intent routing** | Local shell/file operations bypass the LLM entirely when confidence ≥ 0.85 |
| **Vector RAG** | Semantic code search across project files with embedding-based retrieval |
| **Agent routing** | Dynamic agent selection based on capability, cost, latency, load, and reliability |
| **Provider adapters** | Structured message protocol with OpenAI, Anthropic, and generic HTTP provider support |
| **Middleware pipeline** | Retry with exponential backoff, rate limiting, response caching, and request logging |
| **Security hardening** | Argument pattern filtering, shell composition detection, key encryption, audit logging, rate limiting, network egress control |
| **Event tracing** | Every interaction logged to SQLite or JSONL with indexed trace queries |
| **Rust sandbox** | Deterministic subprocess execution with configurable timeouts, byte limits, and policy levels |
| **Rust TUI** | Multi-pane terminal UI with per-agent status, history, and command broadcast |
| **CLI doctor** | System health checks showing all active features, providers, agents, and gateway adapters |

## Quick Start

```bash
# Prerequisites: Python >=3.11, Rust toolchain

# Install Python package
pip install -e .

# Build the Rust runtime (TUI)
cd runtime && cargo build --release --bin elyon-runtime --bin elyon-tui --features tui && cd ..

# Symlink runtime binary
mkdir -p .bin && ln -sf "$(pwd)/runtime/target/release/elyon-tui" .bin/elyon-runtime

# Configure
cp configs/elyon.example.toml elyon.toml

# Launch TUI
elyon
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `elyon` | Launch the TUI (default) |
| `elyon shell` | Interactive REPL |
| `elyon tui` | Launch TUI explicitly |
| `elyon run --prompt <text>` | Send prompt to a single provider |
| `elyon broadcast --prompt <text> --providers p1 p2` | Send prompt to multiple providers in parallel |
| `elyon compile --diagnostics <file>` | Parse a diagnostics JSON file |
| `elyon compile --exec-command <cmd>` | Compile & execute a command through the runtime |
| `elyon repair --diagnostics <file> --attempt <N>` | Attempt to repair code from diagnostics |
| `elyon repair --diagnostics <file> --attempt <N> --apply` | Repair and apply the patch |
| `elyon doctor` | Check system health (features, providers, agents, adapters) |
| `elyon agents` | List detected AI CLI agents |
| `elyon providers` | List configured providers with adapter types |
| `elyon project --file <file>` | Execute a multi-step project from a JSONL task file |
| `elyon project --file <file> --dry-run` | Simulate project execution without side effects |
| `elyon sandbox --command <cmd>` | Run a command through the sandbox policy engine |
| `elyon trace --trace-id <id>` | Replay events for a given trace (intents, providers, memory events) |
| `elyon init --output <path>` | Initialize a new Elyon workspace |

## TUI Hotkeys

| Key | Action |
|-----|--------|
| `q` / `Ctrl+X` | Exit |
| `i` / `Enter` | Enter command mode |
| `Esc` | Cancel / return to normal mode |
| `Up` / `k` | Select previous agent |
| `Down` / `j` | Select next agent |
| `:spawn <name>` | Add a new agent at runtime |

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
adapter = "generic"  # "openai", "anthropic", "generic", "mock"

[agents.planner]
name = "planner"
role = "planner"
provider = "local_mock"
description = "Plans and decomposes tasks"
capabilities = ["code_gen", "debug"]
cost_per_1k_tokens = 0.0

[runtime]
command = [".bin/elyon-runtime"]
request_timeout_seconds = 60.0
```

Set `ELYON_CONFIG` env var or pass `--config <path>` to point at a config file.

### Feature Flags

All upgrades are config-gated and disabled by default:

```toml
[minification]
enabled = true           # Prompt compression (whitespace, labels, JSON)

[cache]
prefix_cache_enabled = true   # Token prefix dedup across turns

[routing]
intent_router_enabled = true  # Local dispatch for shell/file ops

[diff]
enabled = true           # Context diff engine (snapshot + delta)

[knowledge]
vector_enabled = true    # Vector RAG for semantic code search

[session.memory]
enabled = true           # Session summarization (working → summarized → meta)

[agent_routing]
strategy = "cost_efficient"  # "legacy", "cheapest", "fastest", "load_balanced"

[security.sandbox]
enable_argument_filtering = true  # Block dangerous command patterns
enable_composition_check = true    # Block pipes/subshells
deny_privileged_escalation = true  # Block PRIVILEGED policy level
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CLI (Python)                                               │
│  run / broadcast / repair / project / compile / shell / tui  │
├─────────────────────────────────────────────────────────────┤
│  ElyonEngine (orchestration/)                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Minifier │ │ Prefix   │ │ Intent   │ │ Session       │  │
│  │          │ │ Cache    │ │ Router   │ │ Memory        │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Diff     │ │ Vector   │ │ Agent    │ │ Middleware    │  │
│  │ Engine   │ │ RAG      │ │ Router   │ │ Pipeline      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ProviderGateway (providers/)                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ OpenAI   │ │Anthropic │ │ Generic  │ │ Mock / Legacy │  │
│  │ Adapter  │ │ Adapter  │ │ Adapter  │ │ Fallback      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Security Layer (sandbox/)                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Policy   │ │ Arg      │ │ Key      │ │ Audit         │  │
│  │ Engine   │ │ Filter   │ │ Encrypt  │ │ Logger        │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Runtime (Rust)                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ Executor     │ │ Sandbox      │ │ TUI (ratatui)      │  │
│  │ (process mgr)│ │ (policy en.) │ │ (multi-pane)       │  │
│  └──────────────┘ └──────────────┘ └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Event Store

```
┌─────────────────────────────────────────────────────────────┐
│  Event Types                                                │
│  prompt_issued → intent_classified → intent_routed_local    │
│  → provider_requested → provider_responded → memory_events  │
│  → knowledge_retrieved → agent_selected → security_event    │
│  → compile_executed → diagnostic_emitted → repair_generated │
└─────────────────────────────────────────────────────────────┘
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (266 tests)
pytest

# Run benchmarks
pytest tests/benchmarks/

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
│   ├── commands/         # Command implementations (doctor, providers, trace, etc.)
│   └── tui.py            # Python TUI stub (delegates to Rust binary)
├── runtime/              # Rust runtime (executor, sandbox, TUI)
├── orchestration/        # Engine, agents, project planner, minifier, cache, routing, diff
├── providers/            # Provider adapters (OpenAI, Anthropic, Generic, Mock) + gateway + middleware
│   ├── adapters/         # Per-provider serialization/deserialization
│   └── middleware/       # Retry, RateLimit, Cache, Logging
├── state/                # Session state + memory (WorkingMemory, summarization)
├── sandbox/              # Policy engine, arg filtering, audit logger, key encryption, rate limiter
├── compiler/             # Compiler integration, diagnostics parsing
├── telemetry/            # Metrics, logging
├── repair/               # Diagnostic-driven repair loop
├── bindings/             # Language bindings
├── configs/              # Example configs
├── scripts/              # Utility scripts
└── tests/                # 266 tests across all modules
    └── benchmarks/       # Performance benchmarks for all phases
```
