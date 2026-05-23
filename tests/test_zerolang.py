import asyncio
from pathlib import Path
from compiler.zero_compiler import get_ast_skeleton
from orchestration.agents import Agent, AgentSettings, AgentRole

def asyncio_run(coro):
    return asyncio.run(coro)

def test_get_ast_skeleton_python(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text("def hello(name):\n    print(f'Hello {name}')\n\nclass World:\n    pass", encoding="utf-8")
    
    skeleton = asyncio_run(get_ast_skeleton(py_file, zerolang_path="non_existent_binary"))
    assert "def hello(name): ..." in skeleton
    assert "class World: ..." in skeleton

def test_agent_prepare_context(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text("def foo(x): return x", encoding="utf-8")
    
    settings = AgentSettings(name="test-agent", role=AgentRole.PLANNER, provider="mock")
    agent = Agent(settings, zerolang_path="non_existent_binary")
    
    context = asyncio_run(agent.prepare_context([py_file]))
    assert "AST Skeleton:" in context
    assert "def foo(x): ..." in context
