import asyncio
import json
import shutil
from pathlib import Path
from compiler.zero_compiler import get_ast_skeleton
from orchestration.agents import Agent, AgentSettings, AgentRole

ZERO = shutil.which("zero")

def asyncio_run(coro):
    return asyncio.run(coro)

def test_get_ast_skeleton_python(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text("def hello(name):\n    print(f'Hello {name}')\n\nclass World:\n    pass", encoding="utf-8")

    skeleton, knowledge = asyncio_run(get_ast_skeleton(py_file))
    assert "def hello(name): ..." in skeleton
    assert "class World: ..." in skeleton

def test_get_ast_skeleton_zerolang():
    zero_file = Path("native/zero-c/examples/hello.0")
    if not zero_file.exists():
        return
    skeleton, knowledge = asyncio_run(get_ast_skeleton(zero_file))
    assert "fn main Void" in skeleton
    assert len(knowledge) > 0

def test_agent_prepare_context(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text("def foo(x): return x", encoding="utf-8")
    
    settings = AgentSettings(name="test-agent", role=AgentRole.PLANNER, provider="mock")
    agent = Agent(settings, zerolang_path="zero" if ZERO else "non_existent_binary")
    
    context = asyncio_run(agent.prepare_context([py_file]))
    assert "AST Skeleton:" in context
    assert "def foo(x): ..." in context
