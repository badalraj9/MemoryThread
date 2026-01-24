# Contributing to Memory Thread 🧠

Hey! Thanks for checking out Memory Thread. Whether you're fixing a typo or adding a major feature, every contribution matters.

## What is MT?

Memory Thread is an AI memory system — think of it as the "hippocampus" for intelligent agents. It helps AI remember facts, handle contradictions, and know when to say "I don't know."

## The Vibe

We're building something cool here. The core principles:

- **Truth over hacks** — If a shortcut breaks correctness, we don't take it
- **"I don't know" is valid** — Uncertainty is explicit, not hidden
- **Events are immutable** — The past doesn't change

## Quick Start

```bash
# Clone it
git clone https://github.com/your-org/memory-thread.git
cd memory-thread

# Install deps
pip install -r requirements.txt

# Set up your env
cp .env.example .env
# Edit .env with your Postgres credentials
```

**You'll need:**

- Python 3.10+
- PostgreSQL (we use 14+, but 18 works great too)
- Qdrant (vector DB) — optional for basic testing

## Want to Contribute?

### 1. Start with an Issue ✋

Before diving into code, open an issue to discuss what you want to do. Saves everyone time and we can point you in the right direction.

### 2. Fork & Branch

```bash
git checkout -b feature/your-cool-thing
```

### 3. Write Tests

We love tests. If you're adding logic, add a test for it:

```bash
pytest tests/ -v
```

### 4. Submit a PR

Open a PR against `main`. We'll review it, maybe suggest tweaks, and merge it once it's ready.

## Code Style

- **PEP 8** — Standard Python style
- **Type hints** — We use Pydantic, so types matter
- **Comments explain _why_**, not _what_ — The code shows what it does

## Need Help?

- Check the `docs/` folder for architecture details
- Open an issue with questions
- We don't bite! 🙂

## The Bottom Line

This isn't just another CRUD app — it's infrastructure for AI that needs to _remember_. If that excites you, we'd love to have you contribute.

Welcome aboard! 🚀
