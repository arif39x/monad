from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path

BANNER_PATH = Path(__file__).parent.parent / "assets" / "ascii.txt"
IDEAS_PATH = Path(__file__).parent.parent / "elyon-ideas.md"

ABOUT_TEXT = """
\033[1;36mELYON — Multi-Agent Orchestration & Automation Dashboard\033[0m

\033[37mElyon is a deterministic, modular, multi-agent CLI workspace designed
for autonomous software engineering. It detects AI coding agents
installed on your system and orchestrates them through structured
project files — no single-agent lock-in.\033[0m

\033[1;33mSpeciality\033[0m
\033[37m  \033[32m•\033[0m \033[37mAgent-agnostic — works with ANY CLI AI agent you have installed
  \033[32m•\033[0m \033[37mParallel execution — independent tasks run concurrently
  \033[32m•\033[0m \033[37mSandboxed — every subprocess passes through policy enforcement
  \033[32m•\033[0m \033[37mDynamic discovery — finds new agents automatically, no config needed\033[0m

\033[1;33mWhy Elyon is different\033[0m
\033[37m  Unlike single-agent tools, Elyon coordinates multiple specialized
  agents across a project — each handling the tasks they're best
  suited for. It's a conductor, not another musician.\033[0m

\033[1;33mBenefits\033[0m
\033[37m  \033[32m•\033[0m \033[37mNo vendor lock-in — swap agents per task without changing workflows
  \033[32m•\033[0m \033[37mSecurity-first — sandbox policy controls what each agent can do
  \033[32m•\033[0m \033[37mReproducible — JSONL project files version your entire pipeline\033[0m
"""

HELP_TEXT = """
\033[1;36mAvailable commands\033[0m
\033[37m  \033[32mabout\033[0m    \033[37mWhat is Elyon and why it exists
  \033[32mhelp\033[0m     \033[37mShow this help message
  \033[32magents\033[0m   \033[37mDetect and list AI agents installed on your system
  \033[32mconfig\033[0m   \033[37mShow project configuration and template files
  \033[32mproject\033[0m  \033[37mRun a multi-agent project from a JSONL file
  \033[32mrun\033[0m      \033[37mSend a prompt to an LLM provider
  \033[32mcompile\033[0m  \033[37mCheck compilation diagnostics
  \033[32mproviders\033[0m \033[37mList configured LLM providers
  \033[32mdoctor\033[0m   \033[37mCheck system health and configuration
  \033[32m sandbox\033[0m  \033[37mValidate sandbox policy rules
  \033[32mtrace\033[0m    \033[37mLook up an execution trace by ID
  \033[32minit\033[0m     \033[37mGenerate a starter configuration
  \033[32mexit\033[0m     \033[37mExit Elyon (also Ctrl+D or Ctrl+C)\033[0m
"""


def _read_logo() -> list[str]:
    if BANNER_PATH.exists():
        return BANNER_PATH.read_text(encoding="utf-8").splitlines()
    return []


def _format_side_logo(logo_lines: list[str]) -> str:
    lines: list[str] = []
    info = [
        "\033[1;36melyon v0.1.0\033[0m",
        "\033[37mmulti-agent CLI workspace\033[0m",
        "\033[32mtype 'help' for commands\033[0m",
    ]
    term_width = shutil.get_terminal_size().columns

    logo_width = max((len(l) for l in logo_lines), default=0)
    info_width = term_width - logo_width - 5
    if info_width < 20:
        info_width = 20

    for i, logo_line in enumerate(logo_lines):
        stripped = logo_line.rstrip()
        colored_logo = f"\033[36m{stripped}\033[0m"
        if i < len(info):
            padding = " " * 3
            truncated = info[i][:info_width] if len(info[i]) > info_width else info[i]
            lines.append(f"{colored_logo}{padding}{truncated}")
        else:
            lines.append(colored_logo)

    lines.append("")
    return "\n".join(lines)


def print_welcome() -> None:
    logo_lines = _read_logo()
    if logo_lines:
        print(_format_side_logo(logo_lines))
    else:
        term_width = shutil.get_terminal_size().columns
        title = "\033[1;36melyon v0.1.0\033[0m"
        print(f"{title:^{term_width}}")
        print("\033[37mtype 'help' for commands\033[0m".center(term_width))
        print()


def run_interactive() -> None:
    import sys

    print_welcome()

    while True:
        try:
            user_input = input("\033[1;36melyon\033[0m\033[37m> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input in ("exit", "quit", "q"):
            break

        if user_input == "about":
            print(ABOUT_TEXT)
            continue

        if user_input == "help":
            print(HELP_TEXT)
            continue

        if user_input == "agents":
            _handle_agents()
            continue

        if user_input == "config":
            _handle_config()
            continue

        args = shlex.split(user_input)

        if args[0] == "elyon":
            args = args[1:]

        if not args:
            print_welcome()
            continue

        try:
            from cli.main import _build_parser, _run

            parser = _build_parser()
            parsed, _ = parser.parse_known_args(args)

            if parsed.command is None:
                print_welcome()
                continue

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                payload = loop.run_until_complete(_run(parsed))
                from cli.output import render
                print(render(payload, as_json=parsed.json if hasattr(parsed, "json") else False))
            finally:
                loop.close()
        except SystemExit:
            pass
        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m")


def _handle_agents() -> None:
    from orchestration.agent_detector import detect_agents
    from orchestration.adapters.registry import get_adapter
    from orchestration.adapters.base import AdapterContext

    detected = detect_agents()
    if not detected:
        print("\033[33mNo AI agents detected on your PATH.\033[0m")
        return

    print(f"\n\033[1;36mDetected agents ({len(detected)}):\033[0m\n")
    for agent in sorted(detected, key=lambda a: a.name):
        adapter = get_adapter(agent.binary)
        ctx = AdapterContext(prompt="<prompt>", model="<model>")
        cmd = adapter.build_command(agent.binary, ctx)
        signature_display = " ".join(cmd)
        print(f"  \033[32m{agent.name:12}\033[0m  {agent.path}")
        print(f"  {'':12}  \033[90m{agent.description}\033[0m")
        print(f"  {'':12}  \033[90msignature: {signature_display}\033[0m")
        print()
    print(f"\033[90mTip: run 'elyon agents --json' for machine-readable output\033[0m\n")


def _handle_config() -> None:
    import os

    print(f"\n\033[1;36mConfiguration\033[0m\n")
    print(f"  \033[32melyon.toml\033[0m       \033[37mMain config — agents, providers, sandbox policies\033[0m")
    print(f"                     \033[37mMaps CLI agents to project roles\033[0m")

    ideas_exists = IDEAS_PATH.exists()
    ideas_status = "\033[32m✓ exists\033[0m" if ideas_exists else "\033[33mnot yet created\033[0m"
    print(f"  \033[32melyon-ideas.md\033[0m   \033[37mTemplate for project ideas ({ideas_status})\033[0m")
    print(f"                     \033[37mDescribe your project goals, Elyon builds the plan\033[0m")
    print()

    config_dir = Path(os.getcwd())
    toml_path = config_dir / "elyon.toml"
    if toml_path.exists():
        print(f"  \033[90mLocal config: {toml_path}\033[0m\n")
        print(f"  \033[90m{toml_path.read_text()[:600]}\033[0m")
        print()
