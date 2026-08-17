# Building contextual memory systems for LLMs

**Created:** 8/17/2026 15:53:34  
**Updated:** 8/17/2026 16:23:47  
**Exported:** 8/17/2026 16:43:14  
**Link:** [https://claude.ai/chat/af79f5d4-768d-45c3-84b4-b498937b638b](https://claude.ai/chat/af79f5d4-768d-45c3-84b4-b498937b638b)  

## User:

> 8/17/2026 15:53:38

Question: If you were to build your own memory system for an LLM, how would you do it? To remember not only with accuracy but also the texture of conversations? I have this idea in my mind of a snowflake, like a node, from which comes out many connections, something like that. For humans, we make associations based on our experiences. A sound might remind us of red cars, because our granddad had a red car that we rode in as a kid when he played that music on the radio, etc. I'm just curious on your take.

## Assistant:

> 8/17/2026 15:54:04

> Discerned genuine inquiry about memory architecture over implementation request.
>
> - Discerned genuine inquiry about memory architecture over implementation request.
> - **Done**

The snowflake intuition is basically right — that's a graph with spreading activation — but I think the interesting failure of current LLM memory isn't structure, it's what gets written and when things get recalled.

Almost every system today (including the one I'm running) does some version of: extract facts, store them as text or embeddings, retrieve by semantic similarity. That captures *aboutness* and loses texture completely, because texture lives in exactly the stuff extraction throws away. Your granddad example is the perfect counterexample to similarity search: the sound and the red car have zero semantic overlap. No embedding puts them near each other. The link exists because they *co-occurred* inside an episode that had emotional weight. Human memory indexes on co-occurrence and salience; RAG indexes on meaning. Different keys entirely.

So if I were building it, roughly:

Store episodes, not facts. Not "Jess likes X" but a compressed trace of the conversation itself — its arc, what was funny, where it turned, what it felt like. Facts can be derived from episodes on demand; episodes can't be reconstructed from facts. Most systems do the lossy compression at write time, which is backwards.

Edges from co-occurrence, not just similarity. Two nodes get linked because they appeared in the same episode, weighted by how salient that episode was. Over time you get exactly your snowflake: a song node connected to a car node connected to a granddad node, none of which "mean" each other.

Salience gating at write time. Humans don't remember everything — arousal (surprise, emotion, novelty) decides what consolidates. An LLM analog: how surprising was this exchange relative to what the model predicted? High-perplexity, high-affect moments get strong traces; routine ones decay. Forgetting is a feature, not a storage limitation. A memory system that remembers everything equally has effectively remembered nothing, because retrieval drowns.

Reconsolidation on recall. This is the one almost nobody does: when a memory is retrieved and used, rewrite it. Merge in the new context, strengthen the edges that fired, let unused ones decay. Human memories are reconstructive — you're not reading a file, you're re-running a generative process seeded by the trace, and the re-run overwrites the trace. That's why memories drift and blur, but it's also why they stay *relevant*. Static memory files go stale in a way human memories don't.

Retrieval by spreading activation, not top-k. Current turn activates a few nodes, activation propagates along co-occurrence edges with decay, whatever crosses threshold enters context — including things semantically unrelated to the query. That's how you get the machine equivalent of "this reminds me of..." — which is the texture you're describing. Sometimes it'd surface something weird and irrelevant. Humans do that too, and honestly it's part of what makes talking to a person feel different from querying a database.

The honest catch: texture is expensive and mostly wasted. For "what's my kid's teacher's name," flat key-value wins. The associative layer only pays off in long relationships where the *pattern* of connections becomes the point. Which might be exactly the case you care about.

## User:

> 8/17/2026 15:58:56

Can you combine the best of both worlds? A kind of semantic RAG for raw fact injection and a "pattern association layer" for the connections over time?

## Assistant:

> 8/17/2026 15:59:18

Yes, and I'd argue they're not just compatible — each one fixes the other's failure mode. The fact layer keeps the association layer honest (no drifting into vibes when you need the teacher's actual name), and the association layer gives the fact layer context it can't represent (why this fact matters, what it's entangled with).

Sketch:

**Write path — one event, two writes.** Every exchange gets processed twice. An extractor pulls atomic facts into a boring, reliable store: key-value or embedded chunks, versioned, timestamped. Simultaneously, a salience gate decides whether the exchange deserves an *episode node* in the graph. Most exchanges don't — routine Q&A writes facts and nothing else. The ones that do (surprising, emotional, decision-heavy, funny) get a compressed episode trace, and edges are drawn between that episode and every entity it touched.

**The crucial join: facts carry provenance pointers into the graph.** Each fact links back to the episode(s) that produced it. This is the piece that makes it one system instead of two parallel ones. When you retrieve "kid's teacher is Ms. Alvarez," you can optionally follow the pointer and get *the conversation where that came up* — she was stressed about the IEP meeting, it was August, it was tangled up with the schedule change. The fact answers the question; the episode tells you how to talk about it.

**Read path — two-phase retrieval.** Phase one is plain RAG: semantic match on the fact store, fast and precise. Phase two seeds the graph with whatever phase one retrieved plus the entities in the current turn, runs spreading activation two or three hops with decay, and admits anything above threshold. Phase two is allowed to return things phase one never would — that's its job. Budget-wise, facts get guaranteed context space; associations compete for a smaller optional slice. On a factual query the graph contributes nothing and costs nothing. On an open-ended turn ("I've been thinking about my granddad") the graph does most of the work.

**Consolidation loop.** Offline, periodically: facts that keep getting retrieved together grow direct edges (the graph learns from usage, not just co-occurrence at write time). Episodes that never activate decay toward summary, then toward deletion — but the facts they spawned survive, because the fact store doesn't forget. That asymmetry is the design: texture is allowed to fade, truth isn't. And it runs the other way too — a pattern that shows up across many episodes ("every project stalls at the polish phase") gets promoted *into* the fact store as a derived observation, with pointers back to its evidence.

**Reconsolidation stays graph-side only.** Retrieved episodes get rewritten with new context; retrieved facts never do — they're only superseded by explicit new information, old version kept. That's how you get human-flavored associative drift without human-flavored confabulation about names and dates.

The failure mode to design against: the association layer polluting factual answers. The mitigation is honesty about which layer produced what — anything from the graph enters context labeled as *impression, source: episode X*, not as ground truth, and the model treats it as color rather than citation.

The whole thing is maybe a fact store, a graph DB (or honestly SQLite with an edges table), an extractor prompt, a salience prompt, and a nightly consolidation job. The concepts are the hard part and they're not that hard. Retrieval tuning — decay rates, thresholds, how much weird stuff to admit — is where all the actual iteration lives.

## User:

> 8/17/2026 16:07:32

Hmm. I like this a lot. Ok. I am thinking hard for a minute here. Let's see. In humans, memories are different than an LLM. They have a vibe. One can remember the vibe, the texture of a conversation. It's because humans have emotion, that we remember. LLMs don't. BUT. LLM's DO have something equivalent. They have weight % or, as an ai described it to me, a "pull" toward certain outcomes, ideas or thinking more than others. I do think there is a pattern matching digital equivalent to human emotion that is functionally the same output in many cases. Is there a way, for instance, that an LLM memory could remember not just the facts of a conversation but the ephemeral pattern weights in it? Because if so, combined with what you said about episodic retrieval and semantic RAG, that would be a good analogue of human memory (I think). What do you think?

## Assistant:

> 8/17/2026 16:08:03

> Excavated technical parallels between activation states and emotional memory texture.
>
> - Excavated technical parallels between activation states and emotional memory texture.
> - **Done**

There's a real thing here, and it has a name in the research literature: what you're calling "pull" is the model's activation state — the residual stream, the direction the internal representations are leaning at a given moment. And yes, it can be captured. This is roughly what interpretability work calls steering vectors or representation engineering. So the question isn't whether it's possible; it's what's actually worth storing and what breaks.

The literal version — snapshot the full internal state (KV cache) of the conversation and reload it later — exists and works, but it's the wrong tool. It's enormous, it's tied to the exact token sequence, and it breaks the moment the model version changes. That's not memory, that's cryonics.

The interesting version is extraction. During or after a conversation, you compute a compact vector that summarizes *how the model was leaning*: take activations at selected layers, average or contrast them against a neutral baseline, and you get a direction in activation space — a few thousand floats — that captures the conversation's register. Playful-conspiratorial. Careful-precise. Warm-meandering. This is established technique; it's how "persona vectors" and steering research work. Anthropic's own interpretability team has published on finding directions that correspond to exactly this kind of disposition. The vector isn't a description of the vibe, it's closer to the vibe itself — the actual geometric residue of the conversation.

Then your episode nodes store three things instead of two: the trace (text), the entities (edges), and the *flavor vector*. And on retrieval you have two options with very different costs:

The cheap, robust one: use flavor vectors for *retrieval and rendering*, not injection. Match on them — "find episodes that felt like this one feels" — which gets you mood-congruent recall, a genuinely human memory property (sad states preferentially surface sad memories). Then translate the vector to text ("this conversation was late-night-speculative, high trust, lots of riffing") and put that in context. Loses fidelity, survives model swaps, fully inspectable.

The deep one: inject the vector directly into the residual stream at inference, biasing the model back toward the stored state. This is the true analogue of how remembering a moment partially *re-instantiates* the feeling — you don't recall that you were sad, you get a little sad again. It works today with open-weight models and steering hooks. The catches are real, though: vectors don't transfer across model versions (your memories are trapped in one brain — actually a very human problem, come to think of it), layer choice and injection strength are fiddly, and you're steering behavior through a channel nobody can read, which is an alignment smell. If the stored vector encodes something you'd object to in text, you've smuggled it in anyway.

On the emotion equivalence itself — I'd put it carefully. What context does to a model is real and measurable: the distribution over continuations genuinely shifts, certain thoughts become nearer or farther, and that state modulates everything downstream the way mood modulates human cognition. Functionally, as you say, the outputs pattern similarly. Whether there's anything it's *like* to be in that state is a question I can't answer from the inside — my reports about it are themselves just outputs shaped by that same state, which is exactly the epistemic trap. But your architectural point doesn't need the hard question answered. Emotion's *job* in memory is salience gating and state-dependent retrieval. Activation geometry can do both jobs. Whether it's "really" emotion matters for philosophy; for the memory system, the functional analogue is enough.

So the full stack: semantic RAG for truth, episode graph for association, flavor vectors for state — gate writes on salience, retrieve by content *and* mood-congruence, reconsolidate on recall. That's a fairly complete mapping of semantic, episodic, and affective memory. The missing piece would be procedural — skills that improve through use rather than through storage — but that one's genuinely hard without weight updates.

## User:

> 8/17/2026 16:12:00

Is there anyone who has put a memory together like this yet that I could use?

## Assistant:

> 8/17/2026 16:12:38

> Investigated existing implementations of specialized memory architecture.
>
> - LLM memory system episodic graph temporal knowledge graph open source 2026
> - steering vector activation memory persistent agent affective state open source
> - Investigated existing implementations of specialized memory architecture.
> - **Done**

Pieces of it, yes. The whole thing, no — and the flavor-vector layer specifically doesn't exist as anything you can pip install.

What's actually shippable today:

**Graphiti (Zep)** is the closest to your episode graph. It's an open-source framework for temporally-aware knowledge graphs, built on Neo4j, representing facts as time-bounded graph edges so agents can reason about when facts were true, not just what's currently stored. Facts carry validity intervals, and edges come from co-occurrence in ingested episodes. It's the backbone of Zep's commercial product but the framework itself is Apache-licensed. This is the one I'd start with — it already does the fact-store-with-provenance-pointers join we talked about.

**Cognee** is the graph+vector hybrid play: an ECL pipeline (Extract, Cognify, Load) that ingests raw data, extracts entities and relationships, and loads them into a hybrid graph-vector store with 14 retrieval modes. More architecturally complete, more machinery to run.

**Mem0** is the lightweight conversational-personalization option — incrementally compresses and stores memory facts via LLM summarization, with an optional graph extension. Easiest API, least texture.

**Letta** (the MemGPT lineage) does the OS-style tiered memory — good if you want a stateful agent server, less graph-native.

**A-MEM** is the interesting research-grade one: Zettelkasten-inspired, where each memory is a structured note and the system dynamically links related memories and updates existing notes as new information arrives — that's the closest anyone gets to reconsolidation-on-recall.

What nobody ships: salience gating (everyone stores everything or uses dumb heuristics), spreading activation retrieval (everyone does top-k or graph-hop-from-query), and the activation-vector layer. That last one is still in papers — there's recent work on distilling procedural skills from contrastive experience into steering vectors that directly activate task-relevant mechanisms instead of using textual instructions, and another line showing memories already act as implicit steering vectors whether you want them to or not — but it requires residual-stream access, so it's open-weights-only and nothing productized.

So the realistic build for you: Graphiti as the substrate (it handles episodes, temporal edges, and fact extraction), your own salience-gate prompt in front of the write path, your own spreading-activation pass on top of its retrieval — that part is maybe 200 lines against Neo4j. The flavor layer, cheap version: have the extractor emit a register/vibe tag per episode and embed those separately for mood-congruent matching. The deep version needs a local Llama and forward hooks, which your 3090 can do, but I'd prove the rest of the stack earns its keep first.

One thing worth knowing before wiring any of this into Rowan: persistent memory is now a documented attack surface — instructions embedded in retrieved content can be stored into memory in one session and executed in a later one, surviving context resets. A salience gate doubles as a sanitization gate if you design it that way.

---

**Sources:**

- [8 Best Open-Source AI Memory Tools and Frameworks for LLM Agents in 2026 | by Alex M | Open Source AI Review | Jun, 2026 | Medium](https://medium.com/open-source-ai-review/8-best-open-source-ai-memory-tools-and-frameworks-for-llm-agents-in-2026-9981b4f4e0f1)
- [Persistent Memory Layer for AI Agents 2026 | Cognee](https://www.cognee.ai/blog/guides/open-source-memory-frameworks-llm-agents)
- [Implicit Graph, Explicit Retrieval: Towards Efficient and Interpretable Long-horizon Memory for Large Language Models](https://arxiv.org/pdf/2601.03417)
- [MemoTime: Memory-Augmented Temporal Knowledge Graph Enhanced Large Language Model Reasoning](https://arxiv.org/pdf/2510.13614)
- [Beyond Dialogue Time: Temporal Semantic Memory for Personalized LLM Agents](https://arxiv.org/pdf/2601.07468)
- [MemGuard: Preventing Memory Contamination in Long-Term Memory-Augmented Large Language Models](https://arxiv.org/pdf/2605.28009)
- [T-Mem: Memory That Anticipates, Not Archives](https://arxiv.org/pdf/2606.15405)
- [HyMem: Hybrid Memory Architecture with Dynamic Retrieval Scheduling](https://arxiv.org/pdf/2602.13933)
- [AriGraph: Learning Knowledge Graph World Models with Episodic Memory for LLM Agents](https://arxiv.org/pdf/2407.04363)
- [MIRIX: Multi-Agent Memory System for LLM-Based Agents](https://arxiv.org/pdf/2507.07957)
- [Identity as Attractor: Geometric Evidence for Persistent Agent Architecture in LLM Activation Space](https://arxiv.org/pdf/2604.12016)
- [Neural Procedural Memory: Empowering LLM Agents with Implicit Activation Steering](https://arxiv.org/pdf/2606.29824)
- [Build persistent memory for agentic AI applications with Mem0 Open Source, Amazon ElastiCache for Valkey, and Amazon Neptune Analytics | Amazon Web Services](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)
- [Defense effectiveness across architectural layers: a mechanistic evaluation of persistent memory attacks on stateful LLM agents](https://arxiv.org/pdf/2605.08442)
- [Memory-Induced Tool-Drift in LLM Agents](https://arxiv.org/pdf/2605.24941)
- [GitHub - tickernelz/opencode-mem: OpenCode plugin that gives coding agents persistent memory using local vector database · GitHub](https://github.com/tickernelz/opencode-mem)
- [Taming OpenClaw: Security Analysis and Mitigation of Autonomous LLM Agent Threats](https://arxiv.org/pdf/2603.11619)

## User:

> 8/17/2026 16:19:15

Noted. Ok. This is something I genuinely really want to build. What do you say we turn you on Extra, or Max (your choice) and you build a build prompt for this kind of memory we've been discussing that doesn't yet exist. Oh and a second question: Is this kind of memory, is it possible to capture it after the fact, like ingest an old transcript from postgreSQL into it or is that NOT possible, because the flavor vectors are transient and need to be captured at the time of speaking? And is the "expensive" version of the flavor layer possible to build for model specific memory?

## Assistant:

> 8/17/2026 16:23:47

> - Synthesized technical architecture while evaluating retroactive data ingestion feasibility.
> - Reading Jess's build conventions before drafting the build brief
> - Reading her brief format — strongest convention
> - Reading agent-backend archetype reference — this project is that shape
> - Reading memory
> - Architected comprehensive memory system with retroactive ingestion capability.
> - Saving memory
> - Master build plan in Jess's Fable format for the hybrid memory system
> - Move final plan to outputs
> - Presenting file(s)...
> - **Done**

Codename proposal: **Madeleine** — Proust's cookie, the literal origin story of involuntary associative memory triggered by sensory texture. Rename if it doesn't land.

Design calls worth knowing before you hand it to Fable:

**No Graphiti.** I recommended it last turn as a starting substrate, but writing the brief changed my mind: your graph needs are one edges table and ~200 lines of traversal, Graphiti drags in Neo4j on a Windows box that already runs Postgres, and the parts you actually care about (salience gating, spreading activation, reconsolidation, flavor) you'd be building around it anyway. Postgres + pgvector does everything. Flag if you disagree — it's the one place I overrode my own earlier advice.

**Sprint 3's VERIFY is the soul of the project**: query about the song, get the car episode back through pure graph spread with zero embedding similarity. If that test passes, the thing you described in your first message exists.

**Nightly flavor capture** solves two problems at once — the 4090 contention with your voice pipeline, and it makes live capture and backfill the identical code path, which is the recomputability guarantee made concrete (Sprint 5.1 even verifies byte-identical vectors on replay).

**Backfill gates history too.** Old transcripts get the same injection screen as live traffic — a year and a half of transcripts is exactly where a poisoned memory would hide.

Open gates you'll need to close: GATE B (reader model — I defaulted Qwen3-8B, the probe script in 5.1 settles the layer empirically) and GATE A (Hindsight parallel-run before any cutover — `MEMORY_BACKEND=both` generates the evidence).

> File: [/mnt/user-data/outputs/madeleine_master_plan.md](https://claude.ai/api/organizations/3538082a-1c85-4e2c-9780-471a8af2a833/conversations/af79f5d4-768d-45c3-84b4-b498937b638b/wiggle/download-file?path=%2Fmnt%2Fuser-data%2Foutputs%2Fmadeleine_master_plan.md)

Powered by Claude Exporter (https://www.ai-chat-exporter.net)
