# DeepSeek Runtime

> Building a local Agent on the DeepSeek API? Security, multi-step reasoning, cost control, resumability — this repo has you covered.
>
> A fork-ready Python runtime kernel. Clone and go.

[English](README_en.md) | [简体中文](README.md)

***

## Are You Building an Agent on the DeepSeek API?

If you've tried, you've probably seen something like this:

```
You: Read src/main.py from the project directory
Agent: OK, let me call read_file… wait, I can't find the path…
You: ?? Aren't you on my machine?
```

**The core problem**: There's a huge gap between calling an API and building a reliable local Agent.

Calling the API is one line:

```python
requests.post("https://api.deepseek.com/chat/completions", json={...})
```

But making that Agent **safely** read files, run commands, remember state, and not mess up — that requires solving:

- 🔒 **Safety** — Agent might try to execute dangerous commands (`rm -rf /` — what then?)
- 🧠 **Multi-step reasoning** — Agent needs a think→act→observe loop, not a single Q&A
- 📝 **Evidence** — How do you prove the Agent called the API without leaking your API key?
- 💰 **Cost control** — How many tokens were used? What's the cache hit rate?
- 🔄 **Resumability** — If interrupted, can it pick up where it left off instead of starting over?

The API doesn't solve these problems. That's why you need a Runtime.

---

## What Is DeepSeek Runtime?

Imagine you have a brilliant assistant (DeepSeek V4). But it lives in the API server, not on your machine. You want it to read files, search code, modify projects — but it can't touch your computer directly.

**DeepSeek Runtime gives this assistant hands and feet**:

- **Hands** — call tools (read files, run commands)
- **Feet** — limit the action range (project directory only)
- **Brain** — remember where it left off (session state)
- **Mouth** — talk to the API safely (evidence recording, no privacy leaks)
- **Safety officer** — stop dangerous operations anytime (permission policy, rollback)

---

## Quick Start

```bash
# Clone
git clone https://github.com/7colorai/deepseek_runtime.git
cd deepseek_runtime

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
python3 -m pip install -e .

# Health check (no API key needed)
deepseek-runtime doctor --json
```

Got an API key? Run it:

```bash
export DEEPSEEK_API_KEY=sk-your-key-here

# Let the Agent read files and analyze your project
deepseek-runtime run --workspace . "Describe this repository's structure"
```

---

## When Do You Need It

| Scenario | Why Runtime |
|----------|------------|
| You're building on top of the DeepSeek API | Runtime handles safety, sessions, and evidence — you focus on business logic |
| You want a fork-ready Agent kernel | Pure Python, readable, easy to trim down |
| You care about Agent cost and security | Built-in token stats, cache analysis, sandbox isolation, permission policies |
| You want to learn Agent system architecture | Six layers, each file < 500 lines — easy to read and modify |

---

## Six-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLI Layer (cli.py)                             │
│             deepseek-runtime doctor / run                         │
├─────────────────────────────────────────────────────────────────┤
│               Runtime Layer (runtime.py)                          │
│           ReAct Loop: Think→Act→Observe (up to 8 steps)          │
├─────────────────────────────────────────────────────────────────┤
│    Session Layer (session.py)  │  Safety Layer (security.py)     │
│  SessionState / Store          │  Sandbox / Policy / ChangeMgr   │
│  "Short-term memory"           │  "Fence + permissions + rollback"│
├────────────────────────────────┴────────────────────────────────┤
│              Client Layer (client.py)                             │
│     DeepSeekClient: HTTP request + fingerprint + streaming       │
├─────────────────────────────────────────────────────────────────┤
│  Evidence Layer (evidence.py)  │  Observability (observability)  │
│  Hash / Redact / Fingerprint   │  Token / Cache / Cost summary   │
├────────────────────────────────┴────────────────────────────────┤
│           Diagnostics Layer (diagnostics.py)                      │
│     Local health: Python version / API Key / Storage writable    │
└─────────────────────────────────────────────────────────────────┘
```

Each layer is a single file under 500 lines — easy to fork and adapt.

---

## Design Philosophy

### Core Principle: Separate Model Capability from System Capability

| Model (DeepSeek API) | Runtime (this repo) |
|---------------------|-------------------|
| Understand problem, generate response | Tool orchestration and execution |
| Reasoning and planning | Safety boundaries and permission control |
| Code/text generation | Session state persistence |
| Tool-call format output | Evidence with privacy redaction |
| Thinking mode | Token usage and cost estimation |

### One Question Per Layer

**Layer 0: Evidence** → How to prove the Agent really called the API without leaking privacy?
**Layer 1: Client** → How to talk to the API gracefully (fingerprints, streaming, error handling)?
**Layer 2: Session** → How does the Agent remember what it was doing?
**Layer 3: Safety** → What if the Agent tries `rm -rf /`? (Three-layer protection)
**Layer 4: Runtime** → How does the think→act→observe loop work?
**Layer 5: Observability** → How much did it cost, and was it worth it?

---

## Research Lineage

```
llm-harness-agent (theoretical research / 18 deep-dive articles)
    ↓ validate
deepseekagent (end-user product / "one-person company" OS)
    ↓ extract
deepseek_runtime (reusable runtime kernel) ← You are here
```

- Theory → [yuanchenglu/llm-harness-agent](https://github.com/yuanchenglu/llm-harness-agent)
- Product → [yuanchenglu/deepseekagent](https://github.com/yuanchenglu/deepseekagent)
- API Docs → [api-docs.deepseek.com](https://api-docs.deepseek.com/)

---

## Documentation

| Document | Content | Audience |
|----------|---------|----------|
| [API Reference](docs/api.md) | Every public class and method | Developer |
| [Integration Guide](docs/integration-guide.md) | How to integrate Runtime into your app | Developer |
| [Physical Traits](docs/physical-traits.md) | DeepSeek V4 feature support matrix | Architect |
| [Known Unknowns](docs/known-unknowns.md) | Known limitations and future verification | Everyone |
| [Hosting Roadmap](docs/hosting-roadmap.md) | Future multi-tenant hosting plans | CEO/Architect |
| [Security](SECURITY.md) | API key handling, evidence, security reports | Everyone |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions | User |

---

## Release Verification

```bash
# Unit tests
python3 -m unittest discover -s tests -v

# Local health check
deepseek-runtime doctor --json

# Full release drill
python3 scripts/release_drill.py
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json

# Live API smoke test
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json

# Release gate audit
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

---

## License

Apache-2.0. See [LICENSE](LICENSE).

---

> ⭐ If this repo saved you time, give it a star so others can find it.
>
> *Questions? Open an Issue. Want to contribute? PRs welcome.*
