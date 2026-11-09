# Empório da Música — customer service agent

Prototype of a text-message agent for Empório da Música, a fictional musical instrument store in Campo Grande/MS. Built for the Artefact AI Engineer technical challenge.

> Work in progress: this is the project skeleton.

## Running

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add a free API key (Groq or Google AI Studio)
python -m emporio_agent
```

Tests: `python -m unittest`

## Project layout

| Path | Purpose |
|---|---|
| `emporio_agent/cli.py` | Terminal chat loop |
| `emporio_agent/agent.py` | Conversation and tool-calling loop |
| `emporio_agent/llm.py` | Client for the configured LLM provider |
| `emporio_agent/prompts.py` | Persona and behaviour rules |
| `emporio_agent/tools.py` | Tools exposed to the model |
| `emporio_agent/store.py` | Loads and queries the store data |
| `emporio_agent/pricing.py` | Deterministic price and discount rules |
| `emporio_agent/policies.py` | Looks up sections of the policy manual |
| `data/` | Store data, renamed from the challenge files (`products.csv`, `store_policies.pdf`, …) |
| `conversations/` | Example conversations with the agent |

## Technical decisions

TODO: framework, LLM, retrieval architecture, prompt strategy, conversation history, data handling.

## Assumptions

TODO: interpretations made where the brief or the data were ambiguous.

## Known limitations

TODO: what is missing and what I would do with more time.

## Use of coding assistants

TODO: which tools were used and how. Claude Code generated this initial skeleton.
