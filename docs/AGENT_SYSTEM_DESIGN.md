# MT Agent System Design

## Vision: Persistent AI Coding Assistant with Memory

```
┌─────────────────────────────────────────────────────────────────┐
│                    MT Agent Architecture                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Planner   │───▶│   Executor  │───▶│   Verifier  │         │
│  │  (LLM)      │    │  (Tools)    │    │  (Validate)│         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Memory Core (MT)                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  ││
│  │  │ Code Memory  │  │ Task Memory  │  │ Agent Memory     │  ││
│  │  │ (codebase)   │  │ (history)    │  │ (beliefs/tools)  │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Tool Registry

```python
@tool(description="Read file contents")
def read_file(path: str) -> str: ...

@tool(description="Search in files")  
def grep(pattern: str, path: str) -> list: ...

@tool(description="Run shell command")
def run(command: str) -> CommandResult: ...

@tool(description="Edit file")
def edit_file(path: str, old: str, new: str) -> bool: ...
```

### 2. Agent Definition

```python
class Agent:
    name: str              # "CodeReviewer", "BugHunter"
    role: str              # Description of what it does
    tools: List[str]       # Available tools
    memory_type: str       # What it remembers
    
    # Built-in behaviors
    system_prompt: str     # How it thinks
    max_iterations: int    # Timeout
    confidence_threshold: float  # When to stop
```

### 3. Agent Loop

```python
async def agent_run(agent: Agent, task: str):
    # 1. Plan - break task into steps
    plan = llm.plan(task, available_tools=agent.tools)
    
    for step in plan:
        # 2. Execute - run the step
        result = await execute(step, tools=agent.tools)
        
        # 3. Verify - check result
        if not verify(step, result):
            # Retry or escalate
            continue
            
        # 4. Remember - store in MT
        agent.remember(
            content=f"Step: {step}\nResult: {result}",
            source=agent.name,
            confidence=calculate_confidence(result)
        )
        
    # 5. Report - summarize
    return summarize(agent.memories)
```

## Pre-built Agents

| Agent | Specialty | Tools |
|-------|-----------|-------|
| **CodeReviewer** | Find bugs, security issues | read, grep, run |
| **BugHunter** | Reproduce and find root cause | read, run, edit |
| **DocWriter** | Generate docs from code | read, write |
| **TestGen** | Write unit tests | read, write, run |
| **RefactorBot** | Improve code quality | read, edit, run |

## Multi-Agent Collaboration

```python
# Agents can share memory through Galaxy Schema
task = """
Security review of auth.py
  1. CodeReviewer: Find issues
  2. BugHunter: Verify if exploitable
  3. Summarize findings
"""

# Each agent derives beliefs from same code fact
agent1.derive_belief(fact=auth_code, belief="Potential SQL injection")
agent2.derive_belief(fact=auth_code, belief="Not exploitable - uses parameterized query")

# Conflict detection
conflicts = mt.find_conflicts()  # Two agents disagree!
```

## Example Session

```bash
$ mt agent run CodeReviewer --task "Review auth.py"

[CodeReviewer] Analyzing auth.py...
  → Read auth.py (stored in memory)
  → Think: "Search for SQL queries"
  → Grep "query\|execute" → Found 3 locations
  → Think: "Check for SQL injection in line 45"
  → Verified: Uses parameterized queries ✓
  → Remember: "auth.py is safe - no SQL injection"
  
[CodeReviewer] Found 2 minor issues:
  - Hardcoded API key in line 12
  - Missing rate limiting on login endpoint
  
Confidence: 0.85
Memory: Stored 5 insights in MT
```

## Why This Beats Current Solutions

| Feature | OpenCode/Cursor | MT Agent |
|---------|-----------------|----------|
| **Memory** | None (session-based) | Persistent across sessions |
| **Context** | Current file only | Full codebase + history |
| **Multi-agent** | Single AI | Specialized agents with beliefs |
| **Truth tracking** | None | Confidence scores on every finding |
| **Learning** | None | Remembers what worked/didn't |

## Implementation Path

1. **Tool Registry** - Define what agents can do (Week 1)
2. **Agent Class** - Basic agent with memory access (Week 2)
3. **Execution Loop** - Plan → Execute → Verify (Week 3)
4. **Built-in Agents** - CodeReviewer, BugHunter, etc (Week 4)
5. **Multi-agent** - Collaboration via Galaxy Schema (Week 5)

## Files to Create

```
memory_thread/agents/
├── __init__.py
├── base.py          # Agent base class
├── registry.py      # Tool registry
├── executor.py      # Execution loop
├── planner.py       # LLM planning
├── verifier.py      # Result validation
└── builtins/        # Pre-built agents
    ├── code_reviewer.py
    ├── bug_hunter.py
    └── ...
```

---

*This transforms MT from a memory system into an **agentic coding CLI** - persistent, multi-agent, with memory that gets better over time.*