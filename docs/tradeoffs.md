# Design Tradeoffs & Known Limitations

Every decision below had a defensible alternative. This page records which alternative was on the
table, why it lost, and — where the choice was measured rather than argued — what the measurement
said. The point is to make the reasoning inspectable, the same way the wave counts are.

> For how the system works, see [architecture.md](architecture.md). This page is the companion:
> _why_ it works that way, and where the edges are.

## Contents

- [Deliberate tradeoffs](#deliberate-tradeoffs)
- [Known limitations](#known-limitations)
- [What I'd change with more time](#what-id-change-with-more-time)

## Deliberate tradeoffs

### Rules over a learned counter

**Chosen:** an explicit grammar of Elliott Wave rules, checked by per-rule verifiers.
**Alternative:** train a sequence model to label waves end-to-end from price data.

A neural counter would likely read ambiguous charts better than a rule engine — human analysts
disagree precisely because the theory underdetermines those cases, and that is exactly the regime
where a learned prior helps. It was rejected anyway, because it forfeits the thing the project
exists to demonstrate: the per-rule pass/fail trail. A count you cannot interrogate is the status
quo this project is arguing against, and a black-box count with a confidence score attached would
be a _worse_ artifact than a rule-based count with a visible weakest link — more persuasive and
less checkable.

The cost is real and worth naming: **the LLM can never improve the count, only explain it.**

### Weakest-link scoring over a weighted sum

**Chosen:** `score = min(structural_total, visual_total)`, each itself the min of its slot scores.
**Alternative:** a weighted sum of the five scoring slots, with tuned weights.

A weighted sum is easier to tune and produces a smoother ranking, but it lets a hypothesis buy its
way past a broken property with excellence elsewhere — a count with a fatal structural flaw and
beautiful pivots can outrank a merely-good count that breaks nothing. That is not how a human
analyst reads a chart: one fatal flaw discards the count, full stop. The min-composition encodes
that judgment directly.

The cost surfaces in the next tradeoff: a min is flat across everything that isn't the weakest
link, so it discriminates poorly between hypotheses whose weakest links are equally bad.

### The beam dedup key is intentionally coarse

**Chosen:** collapse structurally distinct counts that score identically into one representative.
**Alternative:** refine the dedup key so both variants survive into the beam.

This one was tried and measured, not argued. Refining the key saturates the 500-wide beam
immediately with score-tied variants; score-based truncation then evicts good-but-incomplete
counts that needed a few more segments to prove themselves. **One chart fell from 43 surviving
scenarios to 3.**

The finding underneath: the real limit is that _scoring cannot rank score-tied structural
variants_ — a scoring-model problem, not a dedup problem. Refining dedup without first fixing
scoring just moves the loss somewhere less visible. The coarseness is load-bearing until the
scoring model can break those ties.

### The LLM narrates; it never computes

**Chosen:** a deterministic diagnostics layer (Layer-1) computes every number, and the LLM is
handed that block to describe.
**Alternative:** give the LLM the raw scenario and let it derive targets, risk-reward, and
invalidation levels itself — with tool calls, or with a chain-of-thought pass.

Tool-calling would have been less code than the diagnostics layer. It was rejected because in a
financial context an invented number is the worst possible failure, and "the model usually gets
arithmetic right" is not a property you can gate on. Splitting the pipeline means the number a user
reads is _the same object_ the engine computed — and a fabricated-number check can be a hard
equality test against the Layer-1 block rather than a plausibility judgment.

The same rule reaches the UI: streamed narration skips the typewriter effect for cache hits and
reports real LLM wall time, so the interface never fakes a live model.

### Citations constrained at decode time, not validated afterwards

**Chosen:** the JSON schema's citation field is generated per request as an enum of exactly the
pages the retriever supplied.
**Alternative:** let the model cite freely, then reject or repair responses that cite pages that
weren't retrieved.

Post-hoc validation is the common pattern and it works most of the time — but "most of the time" is
a probabilistic guarantee that degrades with model, temperature, and prompt drift. Constraining the
decode makes citing an unretrieved page **structurally impossible**, and turns a class of bug into
a class of thing-that-cannot-happen. It costs a per-request schema build, which is negligible next
to the LLM call it wraps.

### Single-process caches over a shared store

**Chosen:** parquet cache, LLM response cache, and wave-count memoization all live in-process.
**Alternative:** Redis (or any shared store) from the start.

The deployment pins one worker, where in-process caching is both simpler and strictly faster — no
serialization, no network hop, no extra service to run or pay for. Introducing Redis to a
single-worker demo would be architecture for an audience that doesn't exist.

The cost is that horizontal scaling is blocked until the caches move out: `uvicorn --workers N`
today causes cross-worker cache misses, not corruption. The seams are already behind interfaces
(`BarCache`, and the response cache behind the LLM client), so the swap is contained rather than
cheap-in-theory.

### yfinance as the sole data source

**Chosen:** yfinance — unofficial, unauthenticated, best-effort.
**Alternative:** a licensed market-data feed.

A key-free source is what makes the live demo a link someone can click instead of an account they
have to create, which for a portfolio artifact is the whole point. It's hidden behind the
`BarSource` Protocol, so a licensed feed replaces it without the engine noticing — the engine has
never seen a `DataFrame`.

### No app-level auth or rate limiting

**Chosen:** bound cost with a CORS allowlist, a force-refresh guard, and aggressive caching.
**Alternative:** an auth layer or a rate limiter in front of the API.

The demo's exposure is a public URL with no user accounts and nothing to steal; the actual risk is
**cost**, not access — an anonymous client burning unbounded LLM calls. Each of the three controls
targets that directly: CORS keeps the browser-side surface to the known frontend, the force-refresh
guard (`EWL_DISABLE_FORCE_REFRESH`) blocks the cache bypass that would make repeat calls expensive,
and cached narrations make repeat views free. An auth system would have added a login wall between
a reviewer and the thing they came to look at, to solve a problem the demo doesn't have.

This does not generalize past a demo audience. Anything with real traffic wants a rate limiter or
an auth proxy in front — see the [security checklist](development.md#security-checklist).

## Known limitations

### Citations are a structural guarantee, not a semantic one — and only theory claims carry them

Cited pages are constrained to a per-request whitelist of actually-retrieved pages (an enum at
decode time, plus a gate re-check), so no claim can cite a page that wasn't fetched. Whether that
page's _content_ actually supports the claim is checked only by an opt-in advisory embedding pass,
which is off in the default deployment (it needs the `grounding` extra — ~440MB of torch, well over
Render's free-tier 512MB).

The typing is also what decides which sentences get a citation chip at all. Every sentence is either
a `data_observation` — a number that must appear verbatim in the Layer-1 block — or a `theory_claim`,
which must cite a retrieved page; only the latter produces a chip. A lens whose draft comes back as
data observations alone therefore renders with no citations, which is correct behavior (there is no
theory assertion to source) but reads as a gap if the UI is expected to cite everything.

So: the count is fully verifiable; the narration's grounding is best-effort. Those are different
strengths of claim and the project should not be read as making the stronger one.

**Fixing it would mean:** running the semantic pass by default, which needs an instance sized for
the embedding model — a hosting-cost decision, not a design one.

### Theory provenance

This implements a specific (Thai-sourced) Elliott Wave variant. A few rule boundaries — strict vs
inclusive length comparisons in the 5-wave verifier, the link-wave time gate — are interpretation
calls made from the source text, not settled readings. They are flagged here rather than presented
as canonical, and they await confirmation against the original before being treated as fixed.

### Concurrency ceiling

The synchronous LLM call runs behind `asyncio.to_thread` with no global request deadline, so a
burst of slow cloud calls can saturate the thread pool. Fine at demo scale, where a semaphore
already bounds cloud concurrency (`OLLAMA_CLOUD_CONCURRENCY` — the hosted demo runs four calls in
flight, so a single reading occupies four pool threads for its duration).

**Fixing it would mean:** a bounded executor plus an overall request timeout — small, but untested
under load I haven't generated, so it isn't in.

### Count quality is auditable, not benchmarked

The system can show you exactly _why_ it ranked a count the way it did. What it cannot show you is
a number for how often that ranking agrees with an expert — there is no labeled dataset of
"correct" Elliott Wave counts to score against, and constructing one credibly is a research project
in its own right (analysts disagree; that disagreement is the premise of the whole system).

What exists instead is worked examples, including one the system reads poorly:
[examples.md](examples.md).

**Fixing it would mean:** a labeled corpus and an agreement metric — the honest first step toward
claiming accuracy rather than auditability.

## What I'd change with more time

In priority order, and for stated reasons:

1. **Break score ties in the scoring model**, then revisit the dedup key — the two are one problem,
   and it's the one currently costing the most output quality.
2. **A labeled evaluation set**, even a small hand-built one, to convert "auditable" into a number.
3. **Move the caches behind Redis** — mechanical, and unblocks multi-worker deployment.
4. **Bounded executor + request deadline** on the LLM path, before any traffic that would need it.
