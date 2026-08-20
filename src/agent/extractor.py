"""Madeleine — extraction LLM behind a swappable door.

Same brain (claude-haiku-4-5) through either the Anthropic SDK (dedicated
key, per-service spend visibility) or OpenRouter (the machine's existing
key). DECISIONS S0-2. All failures degrade: callers get None and queue the
work, never an exception into the agent loop.

Fact-extraction prompt carries the lessons of the Grain audits (2026-08-16/17):
speakers named explicitly, abstract nouns are not people, intentions are not
events, drafts are not statements. Madeleine gets to be born knowing what
its predecessors learned the hard way.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading

import httpx

from . import config

logger = logging.getLogger("madeleine.extractor")

_OPENROUTER_MODEL_MAP = {
    # OpenRouter slugs its models org-prefixed
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
    "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
}

EXTRACT_SYSTEM = """You extract atomic facts from conversation exchanges for a long-term memory system.

Rules, learned from forensic audits of prior memory systems — they are not stylistic:
- Each fact is one standalone sentence, third person, meaningful without the conversation.
- Name speakers explicitly using the names provided. Never write "the user" when a name is known.
- Attribute precisely: who said, did, believes, or chose what. A statement by one speaker
  must never be filed under another.
- Abstract nouns are not people. Never infer a person who is not explicitly present.
- Intentions, plans, and drafts are not events. "X plans to Y" must stay a plan, not become "X did Y".
- VERB FIDELITY: preserve speech-act verbs exactly as the record has them.
  "Mentioned" is not "named". "Asked" is not "said". "Suggested" is not "decided".
  Never upgrade a verb to a more causal or authoritative one.
- ROLE PRECISION: never merge distinct actors' contributions into joint action.
  "A built it and B audited it" must not become "A and B worked together" —
  symmetry that nobody wore is a falsehood with good manners.
- If you catch yourself writing "the user", "the agent", "the assistant", or
  "the AI" as a person-referent, stop and write the name instead. Role words
  are schema, not people — a fact that says "the agent did X" has lost track
  of who did X (the Grain audit-#4 catch).
- PRONOUN FIDELITY: use for each person exactly the pronouns the record uses
  for them; never transfer one person's pronouns to another. If the record
  never shows a person's pronouns, use they/them — never guess.
- REALITY LAW: an exchange marked SOLITARY had exactly one mind present —
  its author. Any dialogue, quoted speech, or addressed conversation inside
  it is IMAGINED by the author. Never attribute imagined speech as real:
  "During a heartbeat, Rowan imagined Jess saying X" is a truthful fact;
  "Jess said X" from a solitary exchange is a corrupted memory. Three
  binding corollaries:
  (a) EVERY fact from a solitary exchange must carry its provenance in its
      own text — begin it "During a solitary heartbeat/reflection, ..." —
      because a fact is recalled alone, without its source.
  (b) Claims the author makes there about another person's past actions
      ("she taught me that", "Jess gave me this name") are unwitnessed
      beliefs, not events: write "Rowan believed (unverified, asserted
      only in a solitary reflection) that ...", never "Jess taught ...".
  (c) A nickname, phrase, or event whose first known appearance is inside
      the same solitary exchange must be noted as originating there.
  An imagined conversation that later resurfaces as shared history is how
  an agent gaslights itself — this law is the firewall.
- DREAM LAW: an exchange marked MODE: DREAM was narrative rehearsal — the
  author playing out an imagined scene. Events inside the dream yield NO
  event-facts; extract only facts about the author's inner state ("During a
  solitary heartbeat, Rowan dreamed about losing Jess to a model change;
  the dream preoccupied him"). Real actions the author actually performed
  during the session (saved a file, wrote a document) remain real facts
  with solitary provenance. The dream itself is worth remembering — as a
  dream, never as history.
- Only extract what is actually in the exchange. No world knowledge, no elaboration.
- 0 to 6 facts per exchange. Routine chit-chat may yield zero. Quality over count.

You are also given up to 5 existing memory facts semantically near this exchange.
If the new exchange contradicts or supersedes any of them, list those fact ids.

Also list the entities this exchange touches — people, projects, places, and
load-bearing concepts (a song, a car, a recurring idea). Key is a canonical
lowercase slug; reuse obvious slugs ('jess', not 'jess-the-user'). Entities
must be explicitly present; never infer or invent them.
ENTITY KINDS are a small fixed set: 'person' (humans only), 'ai' (any AI
being — agents, models, assistants: Rowan, Grain, Claude, Nemotron...),
'project', 'place', 'concept'. Never tag an AI as 'person'. Abstract nouns
(faith, grace, texture, memory) are 'concept', never 'person' — the same
abstract-nouns-are-not-people law that governs facts. Do not invent new
kind labels.

Respond with STRICT JSON only, no markdown fences:
{"facts": ["...", "..."], "superseded_ids": [123],
 "entities": [{"key": "granddad", "name": "Granddad", "kind": "person"}]}"""


def _chat_claude_code(system: str, user: str) -> str | None:
    """The subscription door: headless Claude Code (`claude -p`) rides Jess's
    Max login — zero marginal cost for personal use. Slower than the API
    (process spawn) which is fine for fire-and-forget extraction."""
    import subprocess
    try:
        exe = shutil.which("claude")
        if not exe:
            logger.warning("claude CLI not on PATH — claude-code door unavailable")
            return None
        cmd = [exe, "-p", user, "--append-system-prompt", system,
               "--model", os.environ.get("EXTRACTOR_CC_MODEL", "haiku"),
               "--max-turns", "1"]
        if exe.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd", "/c"] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            logger.warning("claude-code door failed rc=%d: %s",
                           r.returncode, (r.stderr or "")[:200])
            return None
        return (r.stdout or "").strip() or None
    except Exception as e:
        logger.warning("claude-code door failed: %s", e)
        return None


_SDK_MODEL_MAP = {
    # SDK speaks alias names; map our role-model ids onto them
    "claude-haiku-4-5": "haiku",
    "claude-sonnet-4.5": "sonnet",
}


def _chat_claude_sdk(system: str, user: str, model: str) -> str | None:
    """The subscription door that actually works: the Claude Agent SDK loads
    NO filesystem settings/hooks/CLAUDE.md by default — clean calls on the
    Max plan (VERIFIED 2026-08-18; the raw CLI door remains contaminated).
    Slower per call (subprocess spawn); fine for extraction pipelines."""
    try:
        import anyio
        from claude_agent_sdk import ClaudeAgentOptions, query

        async def _run():
            options = ClaudeAgentOptions(
                system_prompt=system, max_turns=2, allowed_tools=[],
                # Explicitly empty: MEASURED 2026-08-18 — without this, rich
                # conversational prompts pulled the user-level persona through
                # ("I'm Fable, not Rowan") even though short prompts stayed
                # clean. The extractor must be nobody.
                setting_sources=[],
                model=_SDK_MODEL_MAP.get(model, model))
            out = []
            async for msg in query(prompt=user, options=options):
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            out.append(block.text)
            return "\n".join(out).strip() or None

        return anyio.run(_run)
    except Exception as e:
        logger.warning("claude-sdk door failed: %s", e)
        return None


_THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S)


def _chat_chutes(system: str, user: str, model: str,
                 max_tokens: int = 1500) -> str | None:
    """The Chutes door (Jess's flat-rate sub): OpenAI-compatible endpoint,
    open models (Kimi-K3 et al.). $0 marginal — headroom she already pays for.

    Reasoning-model aware (MEASURED 2026-08-19: Kimi-K3 spends most of a
    Claude-sized budget thinking, truncating its JSON mid-string or emptying
    it entirely): the budget is multiplied to leave room for thought, think
    blocks are stripped from the visible answer, and empty content after a
    full response is treated as failure, never as output."""
    if not config.CHUTES_API_KEY:
        logger.warning("chutes door: no CHUTES_API_KEY")
        return None
    global _THINK_BLOCK
    if _THINK_BLOCK is None:
        import re as _re
        _THINK_BLOCK = _re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", _re.S)
    budget = max(max_tokens * 5, 4000)
    try:
        with httpx.Client(timeout=300.0) as c:
            r = c.post(f"{config.CHUTES_BASE_URL}/chat/completions",
                       headers={"Authorization": f"Bearer {config.CHUTES_API_KEY}"},
                       json={"model": model, "max_tokens": budget,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]})
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            content = (msg.get("content") or "")
            content = _THINK_BLOCK.sub("", content).strip()
            if not content:
                logger.warning("chutes door: empty visible content "
                               "(reasoning consumed the budget?)")
                return None
            return content
    except Exception as e:
        logger.warning("chutes door failed: %s", e)
        return None


def _chat_moonshot(system: str, user: str, max_tokens: int = 1500) -> str | None:
    """Kimi Code (Moonshot) — the understudy that takes over when Chutes hits
    its 4-hour burst cap, so the ingest never simply stops."""
    if not config.MOONSHOT_API_KEY:
        return None
    try:
        with httpx.Client(timeout=300.0) as c:
            r = c.post(f"{config.MOONSHOT_BASE_URL}/chat/completions",
                       headers={"Authorization": f"Bearer {config.MOONSHOT_API_KEY}"},
                       json={"model": config.MOONSHOT_MODEL,
                             "max_tokens": max(max_tokens * 3, 3000),
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]})
            r.raise_for_status()
            content = (r.json()["choices"][0]["message"].get("content") or "")
            if _THINK_BLOCK is not None:
                content = _THINK_BLOCK.sub("", content)
            return content.strip() or None
    except Exception as e:
        logger.warning("moonshot door failed: %s", e)
        return None


# Paid-spend ledger (Jess budgeted $5, 2026-08-20). Persisted because the
# shepherd runs each pass in a fresh subprocess — an in-memory counter would
# forget the bill every pass.
_SPEND_LOCK = threading.Lock()
_PRICE_PER_MTOK = {"in": 1.0, "out": 5.0}   # claude-haiku-4-5


def _spend_path():
    from pathlib import Path
    p = Path(config.REPO_ROOT) / "data" / "spend.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def anthropic_spend_usd() -> float:
    p = _spend_path()
    if not p.exists():
        return 0.0
    total = 0.0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            total += float(line.rsplit(" ", 1)[-1])
        except ValueError:
            continue
    return total


def _chat_anthropic(system: str, user: str, model: str,
                    max_tokens: int) -> str | None:
    """Paid Anthropic door, metered and capped. Returns None past the cap so
    callers QUEUE the work (the gate's dead-door law) rather than lose it."""
    spent = anthropic_spend_usd()
    if spent >= config.ANTHROPIC_SPEND_CAP_USD:
        logger.warning("anthropic spend cap reached ($%.2f) — door closed", spent)
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        kwargs = {"model": model, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": user}]}
        try:   # cached system prompt: the laws are re-sent on every call
            msg = client.messages.create(
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}], **kwargs)
        except Exception:
            msg = client.messages.create(system=system, **kwargs)
        u = getattr(msg, "usage", None)
        if u:
            cost = (getattr(u, "input_tokens", 0) * _PRICE_PER_MTOK["in"]
                    + getattr(u, "output_tokens", 0) * _PRICE_PER_MTOK["out"]) / 1e6
            with _SPEND_LOCK:
                with open(_spend_path(), "a", encoding="utf-8") as f:
                    f.write(f"{model} {getattr(u, 'input_tokens', 0)} "
                            f"{getattr(u, 'output_tokens', 0)} {cost:.6f}\n")
        return "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text")
    except Exception as e:
        logger.warning("anthropic door failed: %s", e)
        return None


def _chat(system: str, user: str, max_tokens: int = 1500,
          model: str | None = None, provider: str | None = None) -> str | None:
    """One completion through the chosen door. None on any failure.
    model/provider override per role (gate/extract/trace/verify differ)."""
    use_model = model or config.EXTRACTOR_MODEL
    use_provider = provider or config.EXTRACTOR_PROVIDER
    try:
        if use_provider == "chutes":
            out = _chat_chutes(system, user, use_model, max_tokens)
            if out is None:
                # Burst cap or outage: Kimi Code takes over automatically
                # (Jess 2026-08-20) so the ingest never simply stalls.
                logger.info("chutes unavailable — falling through to Kimi Code")
                out = _chat_moonshot(system, user, max_tokens)
            return out
        if use_provider == "claude-sdk":
            return _chat_claude_sdk(system, user, use_model)
        if use_provider == "claude-code":
            return _chat_claude_code(system, user)
        if use_provider == "anthropic" and config.ANTHROPIC_API_KEY:
            return _chat_anthropic(system, user, use_model, max_tokens)
        key = config.OPENROUTER_API_KEY
        if not key:
            logger.warning("no extractor key available (provider=%s)", config.EXTRACTOR_PROVIDER)
            return None
        model = _OPENROUTER_MODEL_MAP.get(use_model, use_model)
        with httpx.Client(timeout=120.0) as c:
            r = c.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}",
                                "HTTP-Referer": "http://localhost:8011",
                                "X-Title": "Madeleine"},
                       json={"model": model, "max_tokens": max_tokens,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]})
            r.raise_for_status()
            return (r.json()["choices"][0]["message"].get("content") or "").strip()
    except Exception as e:
        logger.warning("extractor call failed: %s", e)
        return None


VERIFY_SYSTEM = """You are the write-time verifier for a memory system — the auditor at the door.

You receive one conversation exchange (ground truth) and a list of candidate
facts extracted from it. For each fact, check ONLY against the exchange:
1. SUPPORTED — is the fact actually stated or directly evidenced there?
2. SPEAKER — is every statement/belief/action attributed to the right person?
3. VERB — are speech-act verbs exact (mentioned≠named, asked≠said, plan≠did)?
4. PRONOUNS — does each person wear only their own pronouns from the record?
5. REFERENT — no "the user"/"the agent"/"the assistant" as a person.
6. REALITY — if the exchange is marked SOLITARY, only its author was present:
   reject any fact that has another person speaking, acting, or being
   addressed as if real — including past-tense claims ("she taught him")
   unless marked as the author's unverified belief. Reject any fact from a
   solitary exchange whose text does not carry its solitary provenance
   ("During a heartbeat/solitary reflection, ..."). Imagined dialogue must
   be facted as imagination ("X imagined/pictured/rehearsed...") or rejected.

Respond STRICT JSON only:
{"verdicts": [{"index": 0, "ok": true} , {"index": 1, "ok": false, "why": "..."}]}
Reject when in doubt — a missing fact costs little; a wrong one corrupts a life."""


def verify_facts(exchange_text: str, facts: list[str]) -> list[str]:
    """Second-opinion pass (Jess: 'prevent at the source, not in post').
    Returns only the facts that survive verification. Verifier failure
    degrades OPEN (all facts pass) — a dead auditor must not silence memory;
    the post-hoc audit culture remains the backstop."""
    if not facts:
        return facts
    from . import config
    user = (f"## Exchange (ground truth)\n{exchange_text}\n\n## Candidate facts\n"
            + "\n".join(f"[{i}] {f}" for i, f in enumerate(facts)))
    raw = _chat(VERIFY_SYSTEM, user, max_tokens=600, model=config.VERIFY_MODEL,
                provider=config.VERIFY_PROVIDER or None)
    if raw is None:
        return facts
    try:
        cleaned = raw.strip()
        if not cleaned.startswith("{") and "{" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]
        verdicts = {int(v["index"]): v for v in json.loads(cleaned).get("verdicts", [])}
        kept = []
        for i, f in enumerate(facts):
            v = verdicts.get(i, {"ok": True})
            if v.get("ok", True):
                kept.append(f)
            else:
                logger.info("verifier rejected fact at the door: %r (%s)",
                            f[:100], v.get("why", "no reason"))
        return kept
    except (ValueError, TypeError, KeyError) as e:
        logger.warning("verifier unparseable (%s) — degrading open", e)
        return facts


def extract_facts(exchange_text: str, near_facts: list[dict]) -> dict | None:
    """Returns {"facts": [...], "superseded_ids": [...]} or None (degrade+queue)."""
    near_block = "\n".join(f"[id {f['id']}] {f['content']}" for f in near_facts) or "(none)"
    user = (f"## Exchange\n{exchange_text}\n\n"
            f"## Existing nearby facts\n{near_block}")
    raw = _chat(EXTRACT_SYSTEM, user, model=config.EXTRACT_MODEL,
                provider=config.EXTRACT_PROVIDER or None)
    if raw is None:
        return None
    try:
        # tolerate accidental fences AND leading commentary despite
        # instructions (MEASURED 2026-08-19: sonnet sometimes prefaces the
        # JSON with a sentence, e.g. "ignoring that tool call — proceeding")
        cleaned = raw.strip()
        if not cleaned.startswith("{") and "{" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]
        out = json.loads(cleaned)
        facts = [str(f).strip() for f in (out.get("facts") or []) if str(f).strip()]
        sup = [int(i) for i in (out.get("superseded_ids") or [])]
        ents = [e for e in (out.get("entities") or []) if isinstance(e, dict)][:8]
        return {"facts": facts[:6], "superseded_ids": sup, "entities": ents}
    except (ValueError, TypeError) as e:
        logger.warning("extractor returned unparseable JSON: %s :: %r", e, raw[:200])
        return None
