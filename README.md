# Monad-Zero v0.1.0

![Monad Logo](assets/Logo.png)

Monad-Zero is a high-performance, unified AI CLI platform that orchestrates heterogeneous AI agents while achieving >80% token reduction via AST-based "Pre-Flight" context trimming.

## Core Philosophy

- **Unified Interface**: A single, responsive TUI for all your AI agents.
- **Token Efficiency**: Never send full files. Monad-Zero uses ZeroLang to generate AST skeletons, stripping 80%+ of unnecessary tokens before reaching the LLM.
- **Zero-Repair**: A tight feedback loop that validates agent-proposed changes using AST checks, providing surgical diagnostic feedback.
- **Performance**: Rust-powered runtime for near-instant startup and minimal memory footprint.

## Quick Start

1. **Install the platform**:
   ```bash
   pip install -e .
   ```
2. **Build the optimized TUI**:
   ```bash
   cd runtime && cargo build --release --bin monad-tui --features tui && cd ..
   ```
3. **Launch Monad**:
   ```bash
   monad
   ```

## CLI Commands

| Command | Description |
| :--- | :--- |
| `monad` | **(Default)** Launch the unified TUI interface |
| `monad shell` | Open the interactive REPL shell |
| `monad doctor` | Check system health and agent detection |
| `monad agents` | List detected AI CLI agents (aider, claude, etc.) |
| `monad project --file <file>` | Orchestrate a project from a JSONL task file |
| `monad compile --zero <file>` | Compile a `.zero` file and estimate token savings |

## TUI Shortcuts

| Key | Action |
| :--- | :--- |
| `↑` / `↓` | Navigate/Select between detected agents |
| `Enter` | Submit your prompt to the active agent |
| `Backspace` | Edit your current input |
| `Ctrl+X` | **Exit** Monad and return to shell |
| `q` | Exit Monad (alternative) |

## Architecture

- **`cli/`**: Python-based orchestration bridge and user interface routing.
- **`runtime/`**: Ultra-lightweight Rust binary for the TUI and subprocess management.
- **`compiler/`**: The ZeroLang bridge for AST skeleton generation and SDR metrics.
- **`orchestration/`**: Central registry and agent dispatcher logic.

## Optimization: Semantic Density Ratio (SDR)

Monad-Zero tracks the efficiency of its context reduction using the **SDR** metric:
`SDR = (Raw_Token_Count - AST_Token_Count) / Raw_Token_Count`

The system dynamically adjusts AST verbosity to maintain an SDR > 0.6 while ensuring the LLM has sufficient semantic context to perform tasks.

## License

MIT
