# Memory Thread OpenCode Plugin

Native OpenCode plugin that connects OpenCode to Memory Thread's REST API for intelligent context-aware coding.

## Features

- **mt_recall** — Search Memory Thread for relevant context before answering questions
- **mt_remember** — Store important decisions, failures, preferences, and facts
- **mt_check_contradiction** — Check if new info contradicts existing memories
- **mt_status** — View Memory Thread health and stats
- **mt_forget** — Remove specific memories

## Prerequisites

1. **Start MT Server**

```bash
cd memory_thread
mt serve
```

The REST API will be available at `http://localhost:8000`

2. **Initialize a Project**

```bash
cd your-project
mt init
```

This creates `.mt/config.json` with your project namespace.

## Installation

1. Copy the plugin to OpenCode's plugins directory:

```bash
cp integrations/opencode_plugin.ts ~/.config/opencode/plugins/mt_plugin.ts
```

2. Restart OpenCode — the MT tools will be available in your prompts.

## Usage

### mt_recall

```
Search for relevant context:
mt_recall({ query: "how does authentication work", top_k: 5 })
```

### mt_remember

```
Store an important decision:
mt_remember({ content: "We decided to use JWT for auth", type: "decision", confidence: 0.9 })

Store a failure:
mt_remember({ content: "The OAuth integration didn't work, switched to JWT", type: "failure", confidence: 0.8 })

Store a preference:
mt_remember({ content: "I prefer using TypeScript over JavaScript", type: "preference", confidence: 0.7 })

Store a fact:
mt_remember({ content: "User model is defined in models/user.py", type: "fact", confidence: 1.0 })
```

### mt_check_contradiction

```
Before storing, check for contradictions:
mt_check_contradiction({ content: "We switched to PostgreSQL" })
```

### mt_status

```
View health and stats:
mt_status({})
```

### mt_forget

```
Remove a memory:
mt_forget({ entity_id: "abc-123-def" })
```

## Configuration

The plugin automatically resolves namespace from:

1. `.mt/config.json` in current directory
2. Walking up directories (like git)
3. Falls back to `"default"`

To create a project namespace:

```bash
cd your-project
mt init --shared  # For team-shared memories
```

## API Endpoints Used

| Tool | Endpoint | Method |
|------|----------|--------|
| mt_recall | /memory/recall | POST |
| mt_remember | /memory/remember | POST |
| mt_check_contradiction | /memory/check_contradiction | POST |
| mt_status | /health, /stats | GET |
| mt_forget | /memory/:entity_id | DELETE |

## Error Handling

If the MT server is unavailable, tools return a graceful message instead of crashing:

```
MT server unavailable — continuing without memory context (Connection refused)
```
