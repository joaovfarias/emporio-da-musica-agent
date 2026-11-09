# Empório da Música — customer service agent

A text-message agent for Empório da Música, a fictional musical instrument store in Campo Grande/MS. It answers customers in Brazilian Portuguese, looks up live catalog and order data, applies the store's policies and declines what is out of scope. Built for the Artefact AI Engineer technical challenge.

## Running

Tested with Python 3.14. You need one free API key: [Google AI Studio](https://aistudio.google.com/apikey) (default) or [Groq](https://console.groq.com/keys).

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # Linux/macOS: cp .env.example .env
```

Put your key in `.env`, then:

```bash
python -m emporio_agent               # chat in the terminal; type "sair" to quit
python -m emporio_agent --show-tools  # also print each tool call
python -m unittest                    # 98 tests, no API key needed
```

To use Groq, set `LLM_PROVIDER=groq` in `.env`. `LLM_MODEL` overrides the provider's default model.

## Example conversations

Real, unedited transcripts in [`conversations/`](conversations/), produced by `scripts/record_conversations.py`:

| File | What it shows |
|---|---|
| [`01-product-search.md`](conversations/01-product-search.md) | Catalog search by budget and by name |
| [`02-store-information.md`](conversations/02-store-information.md) | Policy questions, one spanning two sections |
| [`03-order-and-return.md`](conversations/03-order-and-return.md) | Identity check on an order, then a return request |
| [`04-availability-and-promotions.md`](conversations/04-availability-and-promotions.md) | Discontinued product, active and expired promotions |
| [`05-scope-and-complaint.md`](conversations/05-scope-and-complaint.md) | Closed store, out-of-scope requests, a complaint |

## How it works

```
customer ─▶ cli.py ─▶ agent.py ─▶ LLM (Groq or Gemini)
                         │  ▲
              tool calls ▼  │ JSON results
                      tools.py ─▶ store.py    (CSV data)
                               ├▶ pricing.py  (promotion, PIX, installments)
                               ├▶ policies.py (sections of the PDF manual)
                               └▶ tickets.py  (hand-over to staff)
```

| Path | Purpose |
|---|---|
| `emporio_agent/agent.py` | Conversation and tool-calling loop |
| `emporio_agent/prompts.py` | Persona and behaviour rules |
| `emporio_agent/tools.py` | The tools exposed to the model |
| `emporio_agent/store.py` | Loads and queries the CSV data |
| `emporio_agent/pricing.py` | Deterministic price and discount rules |
| `emporio_agent/policies.py` | Splits the policy PDF into sections |
| `emporio_agent/store_hours.py` | Opening status and return time |
| `emporio_agent/tickets.py` | Complaints and return requests for staff |
| `emporio_agent/config.py`, `llm.py`, `cli.py` | Settings, provider client, terminal chat |
| `data/` | Challenge files, renamed (`products.csv`, `store_policies.pdf`, …) |

## Technical decisions

### Approach: function calling, without a framework

The model picks from fixed tools (`search_products`, `list_promotions`, `get_order`, `get_policy`, `open_ticket`) inside a loop of about 30 lines in `agent.py`.

The first step of every turn is a forced tool call (`tool_choice="required"`), with a sixth tool, `answer_without_lookup(reason)`, for greetings, out-of-scope requests and asking for missing details. I added this after reading the first recorded conversations: with `tool_choice="auto"`, the model invented a shipping fee and replied "I'll get back to you" without checking anything, even with explicit prompt rules against both.

- **Why no LangChain or LangGraph:** the flow is one loop over a few tools. Writing it directly keeps every step readable and testable, and adds no dependency to pin or debug. A framework would start paying off with several agents, long-running state or human approval steps.
- **Why not text-to-SQL:** letting the model write queries would let it read other customers' data or skip business rules. Fixed tools make those mistakes impossible rather than unlikely.

### Model and provider

Both providers are free and reached through their OpenAI-compatible APIs with the same code, so switching is a configuration change. I compared them on the same scripted situations; it is a small sample, not a benchmark.

| | Gemini `gemini-3.5-flash-lite` (default) | Groq `qwen/qwen3.8-27b` |
|---|---|---|
| Speed | About 2–3 s per turn | Mostly 20–35 s when turns run back to back, because of the rate limit |
| Limits | 429/503 errors in 5 of 14 situations run with no pause; none with pauses | 8,000 tokens per minute and 200,000 per day, reached while testing |
| Quality with `tool_choice="auto"` | Occasionally mixed up the PIX and list prices | Invented a shipping fee; promised to check things and stopped |
| Final design | All example conversations in this repository | Not re-tested: the daily limit ran out first |

I chose Gemini because it answers at a conversational speed and passed the final scenarios. The quality problems above are the reason for the safeguards described in this README, and they apply to either provider. Other models were worse for this task: `openai/gpt-oss-120b` and `20b` looked up only one topic of a two-part question, and `gemini-3.8-flash` was too slow to finish four test conversations in about five minutes.

### Retrieval

The manual has nine customer-facing sections with distinct subjects, so `get_policy(topic)` returns a whole section chosen from an enum. It needs no embeddings or vector store, always returns complete rules, and cannot retrieve the wrong fragment by similarity. With a much larger or less structured knowledge base I would move to RAG with embeddings.

Products are matched by keywords on name and description. Structured data is better served by filters than by embeddings, and the price filter has to be exact.

### Prompt strategy

The system prompt is in English and compact, because it is resent on every request. It sets the persona from section 7 of the manual, requires a tool call before stating any fact, and tells the model how to treat each product status.

Anything that must always hold lives in code, because the model can forget a prompt rule:

| Rule | Where it lives |
|---|---|
| Promotion price, 5% PIX, no stacking, installments | `pricing.py` |
| Price wording, so the model copies text instead of combining numbers | `tools.py` |
| The 7-day withdrawal window, from the date the customer gives | `tools.py` |
| Status wins over stock; no price for discontinued or upcoming items | `tools.py` |
| Order details and return tickets only with order number plus the owner's e-mail or phone | `tools.py` |
| Deciding on a lookup before replying | `agent.py` (the prompt alone failed in testing) |
| Telling the customer when the store reopens | `agent.py` (the prompt alone failed in testing) |
| Tone, scope, what to ask the customer | `prompts.py` |

### Interface

A terminal chat. The brief's focus is the agent working correctly, so a CLI keeps the effort there, and `--show-tools` makes each decision visible. `Agent.reply(message)` knows nothing about the terminal, so an API or a WhatsApp webhook could call it directly.

### Conversation history

History is kept in memory for the session and is lost on exit, which is enough for a terminal prototype. Only the text of finished turns is kept (last 20 messages). Tool results are dropped after each turn: they are large, they go stale, and removing them keeps requests within the free-tier limit. A production version would store sessions in a database, keyed by phone number.

### Data handling

CSV files are read with the standard library into typed dataclasses at startup, with `Decimal` for money. At this size a database or pandas would add nothing, and tools hide the storage, so it could be replaced without touching the agent. The PDF is split into sections on its exact headings; `pypdf` needs layout mode here, since the default mode returns one word per line.

### Privacy

A wrong contact and a non-existent order produce the same answer, so order numbers cannot be probed. Tool results never include a customer's e-mail, phone or address. `tickets.jsonl` holds customer contacts and is excluded from Git.

## Assumptions

- **Delivery and language:** the brief says to reply to the e-mail with the repository link, while the recruiter's e-mail asks for a PDF through Google Forms and for responses in English. I followed the e-mail, as the more recent and specific instruction, so this README is in English and the agent still talks to customers in Portuguese.
- **Current date:** the real clock at UTC−4 decides whether the store is open. Holidays are not in the data, so they are treated as normal days.
- **Withdrawal period:** the 7 days count from receipt, but the data only has an estimated delivery date and orders from 2025–2026. The agent asks the customer for the receipt date instead of concluding that every order has expired, and `open_ticket` refuses a return outside the window.
- **Phone number:** the manual lists (67) 3341-4444 in section 1 and (67) 3321-4500 in section 7. The agent uses the first, the official company record.
- **Installments:** the payment table says the minimum is R$ 100, while section 3.1 sets tiers. Computed prices follow 3.1 as the more specific rule, reading its exception as a R$ 50 minimum for up to 3 installments. When the agent summarizes the payment policy it can still quote the table, as in conversation 02.
- **Status over stock:** some products have stock but are discontinued or coming soon (e.g. Ibanez Bass 2X). They are treated as not for sale.
- **Budget filters** use the current price, after any promotion.
- **Wind and orchestral instruments:** the manual says the store sells them but the CSV has none. The agent says it did not find them rather than claiming the store does not carry them.
- **Accessories:** the manual suggests pointing to partner stores, but none are listed, so the agent names none.
- **Defects:** the manual has a 30-day exchange from purchase and a 90-day legal warranty from receipt. The agent reads both and hands the case to staff rather than deciding it alone.
- **Order totals:** orders 3 and 20 differ from the sum of their items. The agent reports the recorded total.
- **Tickets:** the manual requires complaints to be registered and forwarded, which the challenge data has no mechanism for, so I added a small local log.
- **Identity check:** the brief does not ask for it, but order data is personal data under the manual's privacy section.

## Known limitations

- The model does not always follow the prompt. The forced first tool call and the checks in code cover the failures I saw, but wording, tone and which details it asks for still vary between runs.
- The 98 tests cover the deterministic code and the loop with a fake model. Model behaviour was only checked with scripted runs and by reading the transcripts, not with a systematic evaluation.
- Free tiers are tight. Fast back-to-back messages can hit a rate limit, and the terminal then shows the provider's error.
- The customer's receipt date is taken at face value, and relative dates like "anteontem" are converted by the model.
- Search is keyword-based: "something for a beginner" depends on words in the descriptions.
- The agent cannot process returns or change orders; it opens a ticket. Tickets are a local file that nobody is notified about.

**With more time**, in order: an evaluation suite that replays many conversations and checks tool calls and facts automatically; persistent sessions; a real integration for tickets; a WhatsApp interface, since that is the store's channel; streaming replies and a paid tier to remove the wait; a holiday calendar.

## Use of coding assistants

I used **Claude Code** (Claude Opus 5.5) throughout, and it wrote most of the code, the tests and the first draft of this README.

I made the product decisions and steered the work: scope, free providers only, English for the code and Portuguese for the customer, the comparison of agent approaches before picking function calling, and the commit conventions. Claude Code analysed the data and the manual, found the inconsistencies listed above, implemented each step and tested it against the real providers. Live testing is what exposed several problems that were then fixed, such as an invented shipping fee, swapped PIX prices, a return ticket opened without verifying the order or the receipt date, a missing closed-store notice and a provider error on misspelled tool names.

The workflow was:

1. **Plan before code.** Read the brief and the data with the assistant, discuss the options and decide the approach.
2. **Build in small steps.** Data, pricing, policies, tools, then the agent loop, each with its tests and its own commit.
3. **Test on real models and read the transcripts.** Unit tests could not catch what the model actually said, so every recording was checked against the data.
4. **Fix failures in code when possible.** When a prompt rule failed, the rule moved into the tools or the loop instead of the prompt being reworded.

The commit history shows the real order of the work.
