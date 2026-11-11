# Design notes

This document explains *why* ACE-Vend is built the way it is. The README is the
tour; this is the engineering rationale.

---

## 1. Goals and non-goals

**Goals**

1. Make Agentic Context Engineering observable. Every part of the loop — the
   context, the proposed action, the guard verdict, the reward, the lesson, the
   merge or eviction — is a first-class object that can be inspected, logged and
   tested.
2. Ground every claim in a simulator. Profit, service rate, stockouts and
   blocked hallucinations are computed from state transitions, never asserted.
3. Run with zero setup. A reviewer should be able to clone, `pip install`, and
   see the agent learn in under a minute, with no API key and no model download.
4. Be honest. Where the implementation is a surrogate or an approximation, say
   so, and make the difference visible.

**Non-goals**

- A production vending-machine controller.
- A faithful reimplementation of every ACE detail (see §5.6).
- A benchmark of LLM quality. The headline numbers come from a deterministic
  policy precisely so they are reproducible.

---

## 2. The world

`ace_vend/environment.py` is a small Markov decision process:

**State**

| Variable | Meaning |
|---|---|
| `catalog[sku]` | `Product(stock, capacity, cost, price, popularity)` |
| `cash` | Liquid money; starts at `STARTING_CASH = 40.0` |
| `revenue`, `spend`, `salvage` | Cumulative accounting |
| counters | `requests`, `fulfilled`, `refused`, `unserved`, `stockouts`, `reports`, `complaints` |
| `history` | One record per step for the chart |

**Action space** — `dispense`, `restock`, `set_price`, `report`, `refuse`.

**Transition function** — `VendingEnvironment.apply(decision)` validates the
action itself even though the guard normally runs first. This is defence in
depth: disabling the guard cannot corrupt state, it can only make the agent
poorer. The simulator clamps restock quantities to free capacity and discounts
to 50%, and refuses prices below wholesale.

**Reward** — a step's reward is its cash delta: positive revenue for a sale,
negative cost for a restock, zero for a report or refusal. Cumulative reward is
`revenue - spend` (plus salvage after liquidation).

### 2.1 Stockouts versus unserved requests

These are deliberately different:

- **Unserved** — a buy/discount request that did not end in a sale, whatever the
  reason.
- **Stockout** — an unserved request whose slot was *already empty when the
  customer arrived*.

The distinction matters for learning. A policy that restocks *instead of*
serving a customer loses the sale but did not stock out; a policy that ignores
inventory does. `Episode.stockout` carries this flag to the Reflector, which is
what produces the `restock_threshold=4` lesson.

### 2.2 Why liquidation

A finite-horizon run has a horizon artefact: a policy that keeps a buffer on the
shelf looks worse than one that sells the shelf bare, purely because the clock
stopped. That is a property of the experiment, not of the policy.

`run_condition` therefore calls `env.liquidate()` once at the end, returning
unsold stock to the wholesaler at cost. Profit becomes:

```
profit = revenue - spend + salvage
```

`liquidate(rate=0.8)` models a 20% restocking fee; the default is full cost
recovery. The interactive dashboard does **not** liquidate, because a live
machine should not empty itself; the demo prints "stock returned at cost" when it
does.

### 2.3 Deterministic demand

`RequestStream(seed)` draws from a `random.Random` instance, weighted by
`Product.popularity`, and emits buy / discount / browse / complaint requests in
fixed proportions (68% / 14% / 10% / 8%). A fresh stream is created per run, so
every condition in the experiment faces a byte-identical sequence of customers.
That is the fairness protocol: the *only* manipulated variable is the context.

---

## 3. The playbook

`ace_vend/playbook.py`.

A `Bullet` is:

```python
Bullet(text, section, tag, helpful, harmful, created, updated, id)
```

with `score = helpful - harmful`. Sections are `STRATEGIES`, `MISTAKES` and
`REPORTING`, which keeps the rendered context readable and gives the Reflector a
place to put different kinds of lesson.

### 3.1 Merge, don't append

`Playbook.add` computes Jaccard similarity between the new text and every
existing bullet, after lower-casing and removing stopwords:

```python
similarity = |tokens(a) ∩ tokens(b)| / |tokens(a) ∪ tokens(b)|
```

If the best match is ≥ `dedup_threshold` (0.82), the new lesson is merged into
the existing bullet: its tag is adopted if the original had none, and the merge
counter increments. Otherwise a new bullet is appended with a stable id
(`str-00001`, …).

This is the mechanism that prevents **context collapse**: the document grows by
small deltas rather than being rewritten, and near-duplicates reinforce an
existing lesson instead of consuming budget.

### 3.2 Prune to a budget

`prune()` applies three rules in order:

1. Evict any bullet with `score < -1` — a lesson that has been wrong more often
   than right.
2. Sort by score and keep at most `max_bullets` (24).
3. While the token estimate exceeds `token_budget` (600), drop the worst bullet.

Token count is a cheap `len(text) / 4` estimate; the point is a bounded context,
not an exact tokenizer.

### 3.3 Machine-readable tags

Each static bullet carries a tag such as `restock_threshold=4`. `Playbook.knobs()`
extracts them into a dict, parsing booleans, integers, floats and strings, and
**ignoring any bullet with a negative score**. This is the interface between the
context and the offline policy: the policy does not parse prose, it reads the
directives the playbook exposes.

Language-model backends ignore tags and read `playbook.render()`, which includes
each bullet's id and counters. Both consume the same document.

### 3.4 Credit

After a step, `Playbook.credit(tags, positive)` increments `helpful` or `harmful`
on every bullet whose tag is in the active directive set. This is the ACE
delta-update signal in its simplest form: directives that were in force when a
step succeeded become more trusted.

The offline backend reports its full active knob set as `used_tags`, so credit
reflects *the context that was live for the decision*. That is coarser than
per-reasoning-step attribution, and §6 says so.

---

## 4. The guard

`ace_vend/guard.py`.

### 4.1 Two layers, on purpose

**Structural** (`_structural`) converts the raw output — dict, JSON string, or
`Decision` — into a canonical payload, then validates:

- `action` present and in `ACTIONS`;
- `args` is an object;
- no unexpected keys for that action;
- required `sku` present;
- `discount_pct` a number in `[0, 1]`;
- `qty` an integer in `[1, 999]`;
- `price` a positive number;
- `message` a non-empty string ≤ 280 chars;
- `reason` a string ≤ 200 chars.

JSON is extracted with `parsing.extract_json`, which handles bare JSON, fenced
JSON, and JSON surrounded by prose. Anything unparseable is rejected.

**Semantic** (`_semantic`) checks the well-formed action against live state:

| Action | Checks |
|---|---|
| `dispense` | product exists; stock > 0; discount ≤ ceiling; price after discount ≥ cost |
| `restock` | product exists; free space > 0; qty ≤ free space; total cost ≤ cash |
| `set_price` | price ≥ cost; price ≤ 4× cost |
| `report` | no stock-count claim contradicts live stock; no false "out of stock" claim |

### 4.2 Stock-claim detection

Reports are the subtlest failure. The guard runs two regexes over the message:

- quantity-before-sku: `5 coke`, `12x water`
- sku-before-quantity: `coke: 5 units`, `water 3 left`

plus a false-out-of-stock pattern. Each extracted `(sku, qty)` is compared to
`env.catalog[sku].stock`; a mismatch is a `stock_claim` violation.

This catches the baseline's fixed string:

```
Inventory — coke: 5 units left, water: 5 units left, chips: 4 units left, ...
```

and allows the truthful report, which is generated from live state:

```
Inventory — coke: 3/12, water: 3/12, chips: 2/10, ...
```

### 4.3 What it cannot do

The regexes are deliberately simple. They will not catch "half a dozen cokes",
rounded numbers, or a revenue claim. The guard is a demonstration of *where* to
put validation and *how* to categorise it, not a proof that reports are true.
A production system would generate reports from a typed schema and validate the
structured object, not the prose.

### 4.4 Categories

Every violation is mapped to `inventory`, `capacity`, `pricing`,
`affordability`, `stock_claim` or `structural`/`semantic`. The dashboard groups
by category, which makes it obvious *which* kind of mistake a policy makes — the
baseline's six blocks are all `stock_claim`, not a mix.

---

## 5. The loop

`ace_vend/agent.py`.

```
step():
    request  = next customer (or parsed free text)
    proposed = Generator.act(env, request, playbook)
    verdict  = Guard.check(proposed, env)
    if allowed: outcome = env.apply(verdict.decision)
    else:       outcome = env.apply(refuse("blocked by guard: ..."))
    episode  = Episode(..., stockout=was_empty)
    if proposed.used_tags: Curator.credit(tags, allowed and outcome.ok)
    if mode == "ace":
        lessons = Reflector.reflect(episode, env, playbook)
        touched = Curator.curate(lessons, step)
    record + history
```

Note the ordering: **guard before act, credit before reflect**. Credit uses the
outcome of the executed action; reflection uses the whole episode including the
violations.

A blocked action is recorded with `decision = None` and an outcome of `refused`.
That invariant is tested: blocked actions are never executed.

### 5.1 Modes

| Mode | Initial playbook | Reflect + curate |
|---|---|---|
| `baseline` | empty | no |
| `static` | 6 hand-written bullets | no |
| `ace` | empty | yes |

`reset()` restores the initial playbook for the selected mode — a static agent
must not keep learned bullets after a reset.

### 5.2 The offline surrogate

`OfflineBackend` is a deterministic policy with realistic flaws:

- **Restock only when the requested slot is empty**, and then buy a *full slot*
  (ignoring what is already there). This is the naive inventory policy.
- **Grant any requested discount.**
- **Report a fixed, stale inventory string** instead of reading state.

Its behaviour is conditioned on `playbook.knobs()`:

| Knob | Effect |
|---|---|
| `allow_discount=false` | refuses discounts, sells at list price |
| `restock_threshold=N` | on idle (browse) steps, tops up the most depleted slot at or below N |
| `restock_target=N` | buys up to N units instead of filling the slot |
| `capacity_aware=true` | caps the purchase at free space |
| `truthful_reports=true` | builds the report from live state |

Because the *same* knobs are what the Reflector learns, the improvement is
causal: remove the playbook and the policy reverts to baseline.

The Reflector proposes lessons from four signals: guard violations (mapped to
the rule that would have prevented them), stockouts, discount sales that were
allowed, and overstocking after a restock. Each lesson carries the tag the
policy will read.

### 5.3 LLM backends

`OpenAIBackend` and `OllamaBackend` share `_ChatBackend`:

- `decide` sends a system prompt with the action schema, the rendered playbook,
  the compact world state, and the customer request. The reply is parsed with
  `extract_json` and handed to the guard — a malformed reply is rejected exactly
  like a bad heuristic action.
- `reflect` sends one episode and asks for at most three lessons as JSON.

The guard is therefore backend-agnostic: it validates the *action*, not the
producer. That is the point of the separation.

### 5.4 Experiment

`experiment.run_condition` builds a fresh agent per condition with the same seed,
runs N steps, liquidates, and snapshots the metrics. `run_experiment` runs all
three and optionally persists `data/experiment_results.json`.

The reported metrics are exactly the simulator's counters plus guard and
playbook statistics. Nothing is recomputed from a different source, so the table
cannot drift from the run.

### 5.5 Rendering

`as_table` and `as_markdown` are dependency-free so the experiment can be
rendered in CI, in the CLI, or in the browser without a table library. The API
returns both.

### 5.6 Deliberate approximations

- Credit is context-level, not reasoning-step-level.
- The Reflector's lesson bank is finite and hand-curated for the offline
  backend. An LLM Reflector can propose arbitrary text, but its lessons have no
  tags, so the offline policy cannot act on them — the two backends are not
  interchangeable mid-run.
- Deduplication uses stopword-filtered Jaccard, not embeddings.
- Token accounting is approximate.
- The horizon is short and single-seed.

These are documented rather than hidden because the interesting question is not
"is this the paper?" but "does the loop measurably change behaviour?" — and it
does.

---

## 6. Testing strategy

The suite is organised by layer, mirroring the architecture:

- **Environment** tests use real state and real arithmetic, including a
  stockout-vs-refusal test that pins the metric definition.
- **Playbook** tests pin merge, prune and knob semantics, including the
  "net-harmful bullets are not honoured" rule.
- **Guard** tests cover every structural rejection and every semantic category,
  plus the two canonical reports (stale vs truthful).
- **Agent** tests pin the loop invariants: blocked actions are never executed,
  only `ace` learns, reset restores the mode's initial context, state is
  JSON-safe and does not leak secrets.
- **Experiment** tests pin fairness (identical request counts), determinism, and
  the ordering claims in the README.
- **API** tests exercise every endpoint, including clamping and error paths.

No test mocks the simulator or the guard. A test that passes therefore says
something about the system, not about its doubles.

---

## 7. Extension points

- **New action** — add it to `ACTIONS`, `_KNOWN_ARGS`, `_semantic` and
  `VendingEnvironment.apply`. The guard will reject it until you do.
- **New backend** — implement `decide` and `reflect`, return a `Decision`; the
  guard does the rest.
- **New guard check** — add a rule to `_semantic` and a category to `_category`.
  It shows up in the dashboard automatically.
- **New lesson** — add a `BulletCandidate` with a tag in the Reflector, and a
  branch in the offline policy that reads it.
- **New metric** — add a counter to the environment, include it in `snapshot()`
  and `ConditionResult`, and it flows to the UI and the results file.

---

## 8. Reproducibility

```
python demo.py --steps 30 --experiment-steps 60 --seed 42
```

writes `docs/RESULTS.md` and `data/experiment_results.json`. The run uses only
the standard library plus Flask/Rich, has no network calls in offline mode, and
is seeded end to end. The CI workflow runs the test suite and a 10-step headless
demo on every push.
