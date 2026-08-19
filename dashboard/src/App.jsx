// Madeleine — the Observatory. Not an admin panel: every view is a
// verification instrument. Read-only by design except pin + quarantine
// review ("memory is edited by living, not by clicking").
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

const API = '/api'

// ── Name highlighting ────────────────────────────────────────────────────
// The entities table knows who the people are; the text views wear it.
// Jess (the human) in rose, the agents in sky, other people in violet.
const NameCtx = createContext({ regex: null, colorOf: {} })

const NAME_COLORS = {
  human: 'text-rose-300 font-medium',
  agent: 'text-sky-300 font-medium',
  person: 'text-violet-300 font-medium',
}

function useNameHighlight(scope) {
  const [ents, setEnts] = useState([])
  useEffect(() => {
    fetch(`${API}/entities${scope ? `?scope=${encodeURIComponent(scope)}` : ''}`)
      .then(r => r.json()).then(d => setEnts(d.entities || []))
      .catch(() => setEnts([]))
  }, [scope])
  return useMemo(() => {
    const colorOf = {}
    for (const e of ents) {
      if (!e.name || e.name.length < 3) continue
      const lower = e.name.toLowerCase()
      // an alias wears its person's color (Culurien = Jess)
      const who = (e.alias_target || e.name).toLowerCase()
      if (who === 'jess') colorOf[lower] = NAME_COLORS.human
      else if ((e.kind || '').startsWith('ai') || e.kind === 'agent' ||
               (scope && who === scope.toLowerCase()))
        colorOf[lower] = NAME_COLORS.agent
      else if (e.kind === 'person') colorOf[lower] = NAME_COLORS.person
    }
    const names = Object.keys(colorOf)
    if (!names.length) return { regex: null, colorOf }
    const esc = names.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .sort((a, b) => b.length - a.length)
    return { regex: new RegExp(`\\b(${esc.join('|')})\\b`, 'gi'), colorOf }
  }, [ents, scope])
}

// Text with people lit up. Plain text in, spans out.
const Hi = ({ text }) => {
  const { regex, colorOf } = useContext(NameCtx)
  if (!regex || !text) return text ?? null
  const parts = String(text).split(regex)
  return parts.map((part, i) => {
    const cls = part && colorOf[part.toLowerCase()]
    return cls ? <span key={i} className={cls}>{part}</span> : part
  })
}

// Register text → stable hue (addendum: consistent everywhere)
const hue = (s) => {
  let h = 0
  for (const c of s || '') h = (h * 31 + c.charCodeAt(0)) % 360
  return h
}
const RegisterChip = ({ register }) =>
  register ? (
    <span className="px-2 py-0.5 rounded-full text-xs whitespace-nowrap max-w-full overflow-hidden text-ellipsis"
      title={register}
      style={{ background: `hsl(${hue(register)} 45% 18%)`, color: `hsl(${hue(register)} 70% 75%)` }}>
      {register}
    </span>
  ) : <span className="text-slate-600 text-xs">—</span>

// Compact date chip: true event time when known, else write time
const WhenChip = ({ occurred, created }) => {
  const t = occurred || created
  return t ? (
    <span className="text-xs text-slate-500 whitespace-nowrap"
      title={occurred ? `occurred ${occurred}` : `retained ${created} (no event date)`}>
      {t.slice(0, 16).replace('T', ' ')}{!occurred && '*'}
    </span>
  ) : null
}

const StrengthBar = ({ strength }) => (
  <div className="w-24 h-2 bg-slate-800 rounded overflow-hidden" title={`strength ${strength?.toFixed(2)}`}>
    <div className="h-full rounded transition-all"
      style={{ width: `${Math.min(100, (strength / 2) * 100)}%`,
               background: strength >= 1 ? '#34d399' : strength >= 0.5 ? '#fbbf24' : '#64748b',
               opacity: Math.max(0.35, Math.min(1, strength)) }} />
  </div>
)

const PAGE_SIZE = 50

const Pager = ({ page, setPage, total }) => {
  const pages = Math.max(1, Math.ceil((total || 0) / PAGE_SIZE))
  if (pages <= 1) return null
  const btn = 'px-3 py-1.5 text-xs rounded-lg border border-slate-800 bg-slate-900 ' +
    'text-slate-400 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-default'
  return (
    <div className="flex items-center gap-3 mt-4 text-sm">
      <button className={btn} disabled={page <= 1} onClick={() => setPage(page - 1)}>← prev</button>
      <span className="text-xs text-slate-500">page {page} of {pages}</span>
      <button className={btn} disabled={page >= pages} onClick={() => setPage(page + 1)}>next →</button>
    </div>
  )
}

const SalienceDots = ({ salience }) => (
  <span className="tracking-tighter text-amber-300/90" title={`salience ${salience?.toFixed(2)}`}>
    {'●'.repeat(Math.round((salience || 0) * 5)).padEnd(5, '○')}
  </span>
)

// GitHub-style activity heatmap: exchanges per day, deeper blue = fuller day.
// Dates are true event dates, so a backfilled life paints its real history.
function ActivityMap({ scope }) {
  const [days, setDays] = useState([])
  useEffect(() => {
    fetch(`${API}/activity${scope ? `?scope=${encodeURIComponent(scope)}` : ''}`)
      .then(r => r.json()).then(d => setDays(d.days || [])).catch(() => setDays([]))
  }, [scope])
  if (!days.length) return null
  const byDate = Object.fromEntries(days.map(x => [x.d, x.n]))
  const max = Math.max(...days.map(x => x.n))
  const total = days.reduce((s, x) => s + x.n, 0)
  const peak = days.reduce((a, b) => (b.n > a.n ? b : a))
  const iso = (dt) => dt.toISOString().slice(0, 10)
  const start = new Date(days[0].d + 'T00:00:00Z')
  start.setUTCDate(start.getUTCDate() - start.getUTCDay())   // back to Sunday
  const end = new Date()
  const weeks = []
  const cursor = new Date(start)
  while (cursor <= end) {
    const col = []
    for (let i = 0; i < 7; i++) {
      col.push(iso(cursor))
      cursor.setUTCDate(cursor.getUTCDate() + 1)
    }
    weeks.push(col)
  }
  const monthLabel = (col) => {
    const first = new Date(col[0] + 'T00:00:00Z')
    return first.getUTCDate() <= 7
      ? first.toLocaleString('en', { month: 'short', timeZone: 'UTC' }) : ''
  }
  const shade = (n) => {
    if (!n) return 'rgba(148,163,184,0.07)'
    const t = Math.sqrt(n / max)                       // sqrt: mid days stay visible
    return `rgba(56,189,248,${0.15 + 0.8 * t})`
  }
  return (
    <div className="mt-6 bg-slate-900/70 border border-slate-800 rounded-xl p-4">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500 mb-3">
        <span><span className="text-slate-300">{total.toLocaleString()}</span> exchanges</span>
        <span><span className="text-slate-300">{days.length}</span> active days</span>
        <span>fullest day <span className="text-slate-300">{peak.d}</span> ({peak.n})</span>
      </div>
      <div className="overflow-x-auto">
        <div className="inline-flex gap-[3px]">
          {weeks.map((col, wi) => (
            <div key={wi} className="flex flex-col gap-[3px]">
              <div className="h-3 text-[9px] text-slate-600 leading-3">{monthLabel(col)}</div>
              {col.map(d => (
                <div key={d} title={`${d} — ${byDate[d] || 0} exchanges`}
                  className="w-3 h-3 rounded-[3px]"
                  style={{ background: shade(byDate[d] || 0) }} />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-1.5 mt-2 text-[10px] text-slate-600">
        quieter
        {[0, 0.15, 0.4, 0.7, 1].map(t => (
          <span key={t} className="w-3 h-3 rounded-[3px] inline-block"
            style={{ background: t === 0 ? 'rgba(148,163,184,0.07)' : `rgba(56,189,248,${0.15 + 0.8 * t})` }} />
        ))}
        fuller
      </div>
    </div>
  )
}

function Overview({ scope }) {
  const [stats, setStats] = useState(null)
  useEffect(() => {
    fetch(`${API}/stats${scope ? `?scope=${encodeURIComponent(scope)}` : ''}`)
      .then(r => r.json()).then(setStats)
  }, [scope])
  if (!stats) return <p className="text-slate-500">reading the sky…</p>
  const ep = stats.episodes || {}
  const cards = [
    ['Active facts', stats.facts?.active ?? 0, 'superseded kept: ' + (stats.facts?.superseded ?? 0)],
    ['Episodes strong', ep.strong ?? 0, `${ep.mid ?? 0} mid · ${ep.faint ?? 0} faint`],
    ['Edges', stats.edges ?? 0, `${stats.entities ?? 0} entities`],
    ['Quarantined', ep.quarantined ?? 0, `${ep.pinned ?? 0} pinned`],
    ['Raw exchanges', stats.raw_exchanges ?? 0, 'replay store (never retrieved)'],
  ]
  const lc = stats.last_consolidation
  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {cards.map(([label, n, sub]) => (
          <div key={label} className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
            <div className="text-3xl font-semibold text-sky-200">{n}</div>
            <div className="text-sm text-slate-400 mt-1">{label}</div>
            <div className="text-xs text-slate-600 mt-1">{sub}</div>
          </div>
        ))}
      </div>
      <ActivityMap scope={scope} />
      {lc && (
        <div className="mt-6 bg-slate-900/70 border border-slate-800 rounded-xl p-4 text-sm">
          <div className="text-slate-400 mb-2">Last consolidation — {lc.started?.slice(0, 16)}</div>
          <div className="flex flex-wrap gap-4 text-slate-300">
            <span>decayed {lc.decayed}</span><span>reconsolidated {lc.reconsolidated}</span>
            <span>compressed {lc.compressed}</span><span>tombstoned {lc.tombstoned}</span>
            <span>patterns {lc.patterns_promoted}</span>
            <span>co-retrieval edges {lc.co_retrieval_edges}</span>
            <span>projected {lc.projected}</span>
            {lc.errors?.length > 0 && <span className="text-rose-400">errors {lc.errors.length}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

function Dossier({ id, onClose }) {
  const [ep, setEp] = useState(null)
  const load = useCallback(() => {
    fetch(`${API}/episodes/${id}`).then(r => r.json()).then(setEp)
  }, [id])
  useEffect(load, [load])
  if (!ep) return null
  return (
    <div className="fixed inset-0 bg-black/60 z-20 flex justify-end" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-xl h-full overflow-y-auto bg-slate-950 border-l border-slate-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg text-sky-200">Episode {ep.id}</h2>
          <div className="flex gap-2">
            <button className="text-xs border border-slate-700 rounded px-2 py-1 hover:bg-slate-800"
              onClick={() => fetch(`${API}/episodes/${ep.id}/pin`, { method: 'POST' }).then(load)}>
              {ep.pinned ? '📌 pinned (decay-exempt)' : 'pin'}
            </button>
            <button className="text-xs text-slate-500 px-2" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-3 text-sm">
          <RegisterChip register={ep.register} />
          <SalienceDots salience={ep.salience} />
          <StrengthBar strength={ep.strength} />
          {ep.mode === 'dream'
            ? <span title="a dream — narrative rehearsal during solitary time; its events did not happen">💭 dream</span>
            : ep.solitary && <span title="solitary — the agent's own time; any company in this memory was imagined">🌙 solitary{ep.mode ? ` · ${ep.mode}` : ''}</span>}
          {ep.quarantined && <span className="text-rose-400 text-xs">QUARANTINED</span>}
        </div>
        <p className="text-slate-200 leading-relaxed mb-4"><Hi text={ep.trace} /></p>
        <div className="text-xs text-slate-500 mb-4">
          recalls {ep.recall_count} · last {ep.last_recalled_at?.slice(0, 16) || 'never'} ·
          occurred {ep.occurred_at?.slice(0, 16) || '—'}
        </div>
        {ep.entities?.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm text-slate-400 mb-2">Entities touched</h3>
            <div className="flex flex-wrap gap-2">
              {ep.entities.map(e => (
                <span key={e.id} className="text-xs border border-slate-700 rounded-full px-2 py-0.5">
                  {e.name} <span className="text-slate-600">w{e.weight?.toFixed(1)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
        {ep.facts?.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm text-slate-400 mb-2">Facts born here</h3>
            {ep.facts.map(f => (
              <p key={f.id} className={`text-sm mb-1 ${f.status === 'superseded' ? 'line-through text-slate-600' : 'text-slate-300'}`}>
                <Hi text={f.content} /> {f.kind === 'derived' && <span className="text-violet-400 text-xs">derived</span>}
              </p>
            ))}
          </div>
        )}
        {ep.revisions?.length > 0 && (
          <div>
            <h3 className="text-sm text-slate-400 mb-2">Revision history (what this memory used to say)</h3>
            {ep.revisions.map(r => (
              <div key={r.id} className="border-l-2 border-slate-700 pl-3 mb-3">
                <div className="text-xs text-slate-500">{r.reason} · {r.rewritten_at?.slice(0, 16)}</div>
                <p className="text-sm text-slate-400 italic">{r.trace}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Episodes({ scope }) {
  const [data, setData] = useState({ episodes: [], total: 0 })
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('created_at')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(null)
  useEffect(() => { setPage(1) }, [q, sort, scope])
  useEffect(() => {
    const t = setTimeout(() =>
      fetch(`${API}/episodes?sort=${sort}&page=${page}&page_size=${PAGE_SIZE}` +
            `${q ? `&q=${encodeURIComponent(q)}` : ''}` +
            (scope ? `&scope=${encodeURIComponent(scope)}` : ''))
        .then(r => r.json()).then(setData), 200)
    return () => clearTimeout(t)
  }, [q, sort, scope, page])
  return (
    <div>
      <div className="flex gap-3 mb-4">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="search trace or register…"
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm flex-1" />
        <select value={sort} onChange={e => setSort(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm">
          {['created_at', 'occurred_at', 'salience', 'strength', 'recall_count'].map(s =>
            <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="text-slate-500 text-sm self-center">{data.total} episodes</span>
      </div>
      <div className="space-y-2">
        {data.episodes.map(ep => (
          <div key={ep.id} onClick={() => setOpen(ep.id)}
            className={`bg-slate-900/60 border rounded-xl px-4 py-3 cursor-pointer hover:border-sky-800
              ${ep.quarantined ? 'border-rose-900/60 opacity-60' : 'border-slate-800'}`}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-1">
              <RegisterChip register={ep.register} />
              <SalienceDots salience={ep.salience} />
              <StrengthBar strength={ep.strength} />
              {ep.mode === 'dream'
                ? <span title="a dream — narrative rehearsal during solitary time; its events did not happen">💭</span>
                : ep.solitary && <span title="solitary — the agent's own time; any company in this memory was imagined">🌙</span>}
              {ep.mode && ep.mode !== 'dream' && <span className="text-xs text-slate-600">{ep.mode}</span>}
              {ep.pinned && <span title="pinned">📌</span>}
              {ep.quarantined && <span className="text-rose-400 text-xs">QUARANTINED</span>}
              <span className="text-xs text-slate-600 ml-auto flex items-center gap-3">
                <WhenChip occurred={ep.occurred_at} created={ep.created_at} />
                <span>recalls {ep.recall_count}</span>
              </span>
            </div>
            <p className="text-sm text-slate-300 line-clamp-2"><Hi text={ep.trace} /></p>
          </div>
        ))}
        {data.episodes.length === 0 && (
          <p className="text-slate-600 text-sm">No episodes yet — memory is waiting to live a little.</p>
        )}
      </div>
      <Pager page={page} setPage={setPage} total={data.total} />
      {open && <Dossier id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function Facts({ scope }) {
  const [data, setData] = useState({ facts: [], total: 0, mode: 'list' })
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('created_at')
  const [page, setPage] = useState(1)
  useEffect(() => { setPage(1) }, [q, scope, status, sort])
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams()
      if (scope) p.set('scope', scope)
      if (q.trim()) p.set('q', q.trim())
      if (status) p.set('status', status)
      if (sort) p.set('sort', sort)
      p.set('page', page); p.set('page_size', PAGE_SIZE)
      fetch(`${API}/facts?${p}`).then(r => r.json()).then(setData)
    }, 300)
    return () => clearTimeout(t)
  }, [q, scope, status, sort, page])
  return (
    <div>
      <div className="flex gap-3 mb-4">
        <input value={q} onChange={e => setQ(e.target.value)}
          placeholder="semantic search (live pgvector cosine)…"
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm flex-1" />
        <select value={status} onChange={e => setStatus(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm">
          <option value="">all statuses</option>
          <option value="active">active</option>
          <option value="superseded">superseded</option>
        </select>
        <select value={sort} onChange={e => setSort(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm">
          <option value="created_at">newest written</option>
          <option value="occurred_at">by event date</option>
        </select>
        <span className="text-slate-500 text-sm self-center">
          {data.total} facts · {data.mode === 'semantic' ? 'ranked by cosine'
            : sort === 'occurred_at' ? 'by event date' : 'newest first'}
        </span>
      </div>
      <div className="space-y-1.5">
        {data.facts.map(f => (
          <div key={f.id}
            className={`bg-slate-900/50 border border-slate-800/70 rounded-lg px-4 py-2.5 text-sm
              ${f.status === 'superseded' ? 'opacity-50' : ''}`}>
            <span className={f.status === 'superseded' ? 'line-through text-slate-500' : 'text-slate-200'}>
              <Hi text={f.content} />
            </span>
            <span className="text-xs text-slate-600 ml-2">
              {(f.occurred_at || f.created_at) && (
                <span className="text-slate-500 mr-2"
                  title={f.occurred_at ? `occurred ${f.occurred_at}` : `retained ${f.created_at} (no event date)`}>
                  {(f.occurred_at || f.created_at).slice(0, 16).replace('T', ' ')}{!f.occurred_at && '*'}
                </span>
              )}
              {f.kind === 'derived' && <span className="text-violet-400 mr-2">derived</span>}
              {f.status === 'superseded' && <span className="mr-2">→ #{f.superseded_by}</span>}
              {f.similarity != null && <span className="text-emerald-500 mr-2">cos {f.similarity.toFixed(3)}</span>}
              {f.source_episode_id && <span className="mr-2">ep {f.source_episode_id}</span>}
              <span>{f.source_ref}</span>
            </span>
          </div>
        ))}
        {data.facts.length === 0 && (
          <p className="text-slate-600 text-sm">No facts here yet — truth accumulates one exchange at a time.</p>
        )}
      </div>
      {data.mode !== 'semantic' && <Pager page={page} setPage={setPage} total={data.total} />}
    </div>
  )
}

function Playground({ scope: navScope }) {
  const [scope, setScope] = useState(navScope || 'companion')
  useEffect(() => { if (navScope) setScope(navScope) }, [navScope])
  const [query, setQuery] = useState('')
  const [mood, setMood] = useState('')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!query.trim()) return
    setBusy(true)
    try {
      const r = await fetch(`${API}/recall`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope, query, mood_text: mood || null, debug: true }),
      })
      setOut(await r.json())
    } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="flex gap-3 mb-4 flex-wrap">
        <input value={scope} onChange={e => setScope(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm w-36" title="scope" />
        <input value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
          placeholder="ask the memory…" className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm flex-1" />
        <input value={mood} onChange={e => setMood(e.target.value)}
          placeholder="mood (optional): late-night, wistful…"
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm w-64" />
        <button onClick={run} disabled={busy || !query.trim()}
          className="bg-sky-700 hover:bg-sky-600 disabled:opacity-40 rounded-lg px-4 py-2 text-sm">
          {busy ? 'recalling…' : 'Recall'}
        </button>
      </div>
      {out && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
            <h3 className="text-sm text-emerald-300 mb-2">Facts (phase 1 — truth)</h3>
            {out.facts?.length ? out.facts.map(f => (
              <p key={f.id} className="text-sm text-slate-300 mb-2">
                {f.content} <span className="text-xs text-slate-600">cos {f.similarity}</span>
              </p>
            )) : <p className="text-slate-600 text-sm">none</p>}
          </div>
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
            <h3 className="text-sm text-violet-300 mb-2">Associations (phase 2 — impressions)</h3>
            {out.associations?.length ? out.associations.map(a => (
              <div key={a.episode_id} className="mb-3">
                <p className="text-sm text-slate-300 italic">impression: {a.trace}</p>
                <div className="text-xs text-slate-600 mt-1 flex gap-2 items-center flex-wrap">
                  <RegisterChip register={a.register} />
                  <span>activation {a.activation}</span>
                  {a.mood_similarity != null && <span>mood {a.mood_similarity}</span>}
                </div>
              </div>
            )) : <p className="text-slate-600 text-sm">the graph owed nothing</p>}
          </div>
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
            <h3 className="text-sm text-amber-300 mb-2">Debug (how it thought)</h3>
            <p className="text-xs text-slate-500 mb-1">seeds: {out.debug?.seeds?.join(', ') || '—'}</p>
            {out.debug?.hops?.map((hop, i) => (
              <div key={i} className="text-xs text-slate-500 mb-1">
                hop {i + 1}: {hop.length ? hop.map(h => `${h.node}@${h.activation}`).join('  ') : 'quiet'}
              </div>
            ))}
            <p className="text-xs text-slate-600 mt-2">
              candidates {out.debug?.candidates ?? 0} → packed {out.debug?.packed ?? 0}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

function Atlas({ scope }) {
  const [space, setSpace] = useState('register')
  const [points, setPoints] = useState([])
  const [links, setLinks] = useState([])
  const [showLinks, setShowLinks] = useState(false)
  const [view, setView] = useState('map')          // 'map' | 'flavors'
  const [hiReg, setHiReg] = useState('')           // register highlight from census
  const [hover, setHover] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => {
    const p = new URLSearchParams({ space })
    if (scope) p.set('scope', scope)
    if (showLinks) p.set('links', 'true')
    fetch(`${API}/atlas?${p}`).then(r => r.json())
      .then(d => { setPoints(d.points || []); setLinks(d.links || []) })
      .catch(() => { setPoints([]); setLinks([]) })
  }, [space, scope, showLinks])
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const pad = 0.08
  const x0 = Math.min(...xs), x1 = Math.max(...xs)
  const y0 = Math.min(...ys), y1 = Math.max(...ys)
  const sx = x => 60 + ((x - x0) / ((x1 - x0) || 1)) * 680 * (1 - pad)
  const sy = y => 40 + ((y - y0) / ((y1 - y0) || 1)) * 440 * (1 - pad)
  const pos = {}
  for (const p of points) pos[p.id] = [sx(p.x), sy(p.y)]
  const dimmed = (p) => hiReg && !(p.register || '').toLowerCase()
    .includes(hiReg.toLowerCase())
  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 mb-3">
        <div className="flex rounded-lg overflow-hidden border border-slate-800">
          {['map', 'flavors'].map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs ${view === v ? 'bg-sky-900/60 text-sky-200' : 'bg-slate-900 text-slate-500'}`}>
              {v}
            </button>
          ))}
        </div>
        {view === 'map' && (<>
        <div className="flex rounded-lg overflow-hidden border border-slate-800">
          {['register', 'flavor'].map(s => (
            <button key={s} onClick={() => setSpace(s)}
              className={`px-3 py-1.5 text-xs ${space === s ? 'bg-sky-900/60 text-sky-200' : 'bg-slate-900 text-slate-500'}`}>
              {s} space
            </button>
          ))}
        </div>
        <button onClick={() => setShowLinks(v => !v)}
          className={`px-3 py-1.5 text-xs rounded-lg border ${showLinks
            ? 'border-emerald-800 bg-emerald-900/40 text-emerald-200'
            : 'border-slate-800 bg-slate-900 text-slate-500'}`}>
          {showLinks ? `links on (${links.length})` : 'links off'}
        </button>
        {hiReg && (
          <button onClick={() => setHiReg('')}
            className="px-3 py-1.5 text-xs rounded-lg border border-amber-800 bg-amber-900/40 text-amber-200">
            highlighting “{hiReg.slice(0, 40)}” ✕
          </button>
        )}
        <span className="text-xs text-slate-500">
          {points.length} episodes · color = register · size = salience · fade = strength
        </span>
        {space === 'flavor' && points.length === 0 && (
          <span className="text-xs text-amber-400">
            no flavor projections yet — the reader captures in the nightly window
          </span>
        )}
        </>)}
      </div>
      {view === 'flavors' ? (
        <FlavorCensus scope={scope} onPick={r => { setHiReg(r); setView('map') }} />
      ) : (<>
      <svg viewBox="0 0 760 500" className="w-full bg-slate-950/60 border border-slate-800 rounded-xl">
        {showLinks && links.map((l, i) => {
          const a = pos[l.a], b = pos[l.b]
          if (!a || !b) return null
          return <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
            stroke={l.kind === 'co_retrieval' ? '#34d399' : '#f59e0b'}
            strokeWidth={Math.min(2.5, 0.4 + l.weight * 0.3)}
            opacity={Math.min(0.55, 0.12 + l.weight * 0.08)} />
        })}
        {points.map(p => (
          <circle key={p.id} cx={sx(p.x)} cy={sy(p.y)}
            r={3 + (p.salience || 0.5) * 7}
            fill={`hsl(${hue(p.register || '')} 65% 60%)`}
            stroke={hiReg && !dimmed(p) ? '#fbbf24' : 'none'} strokeWidth={2}
            opacity={dimmed(p) ? 0.08
              : Math.max(0.25, Math.min(0.95, p.strength || 1))}
            className="cursor-pointer"
            onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
            onClick={() => setOpen(p.id)} />
        ))}
        {hover && (() => {
          const label = `#${hover.id} · ${hover.register || ''}`
          const line1 = label.slice(0, 96)
          const line2 = label.slice(96, 192)
          const twoLines = line2.length > 0
          return (
            <g>
              <rect x={20} y={twoLines ? 438 : 455} width={720}
                height={twoLines ? 55 : 38} rx={8}
                fill="#0f172acc" stroke="#1e293b" />
              <text x={32} y={twoLines ? 460 : 478} fill="#cbd5e1" fontSize="12">
                {line1}
              </text>
              {twoLines && (
                <text x={32} y={478} fill="#cbd5e1" fontSize="12">{line2}</text>
              )}
            </g>
          )
        })()}
      </svg>
      </>)}
      {open && <Dossier id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// The flavor census: deep flavor is a continuous field — these are its named
// shadows. Exact register tags, counted. A tag that recurs is a mood the
// reader keeps finding. Click one to see where it lives on the map.
function FlavorCensus({ scope, onPick }) {
  const [data, setData] = useState({ registers: [], distinct: 0, episodes: 0 })
  const [q, setQ] = useState('')
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams()
      if (scope) p.set('scope', scope)
      if (q.trim()) p.set('q', q.trim())
      fetch(`${API}/registers?${p}`).then(r => r.json()).then(setData)
        .catch(() => {})
    }, 250)
    return () => clearTimeout(t)
  }, [scope, q])
  return (
    <div>
      <div className="flex gap-3 mb-3 items-center">
        <input value={q} onChange={e => setQ(e.target.value)}
          placeholder="search flavors… (e.g. warm, debugging, teasing)"
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm flex-1" />
        <span className="text-xs text-slate-500">
          {data.distinct} distinct moods across {data.episodes} episodes
        </span>
      </div>
      <p className="text-xs text-slate-600 mb-3">
        deep flavor is a gradient, not a checklist — these are the reader's named
        shadows of it, counted exactly. click one to light it up on the map.
      </p>
      <div className="space-y-1">
        {data.registers.map(r => (
          <div key={r.register} onClick={() => onPick(r.register)}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-slate-900/50 border border-slate-800/70 rounded-lg px-3 py-2 cursor-pointer hover:border-amber-800">
            <span className="text-sm font-medium w-10 text-right"
              style={{ color: `hsl(${hue(r.register)} 70% 70%)` }}>{r.n}×</span>
            <RegisterChip register={r.register} />
            <SalienceDots salience={r.avg_salience} />
            <span className="text-xs text-slate-600 ml-auto whitespace-nowrap">
              {r.first_seen?.slice(0, 10)} → {r.last_seen?.slice(0, 10)}
            </span>
          </div>
        ))}
        {data.registers.length === 0 && (
          <p className="text-slate-600 text-sm">No flavors named yet.</p>
        )}
      </div>
    </div>
  )
}

// Hindsight-style entity roster: who and what memory touches, how often,
// and when they were first and last seen.
function Entities({ scope }) {
  const [ents, setEnts] = useState([])
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(200)
  const [open, setOpen] = useState(null)
  useEffect(() => { setLimit(200) }, [scope, q])
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams()
      if (scope) p.set('scope', scope)
      if (q.trim()) p.set('q', q.trim())
      p.set('limit', limit)
      fetch(`${API}/entities?${p}`).then(r => r.json())
        .then(d => setEnts(d.entities || [])).catch(() => setEnts([]))
    }, 250)
    return () => clearTimeout(t)
  }, [scope, q, limit])
  const kindColor = { person: 'text-violet-300', ai: 'text-sky-300',
    agent: 'text-sky-300', project: 'text-emerald-300', place: 'text-amber-300',
    concept: 'text-slate-300' }
  return (
    <div>
      <div className="flex gap-3 mb-4">
        <input value={q} onChange={e => setQ(e.target.value)}
          placeholder="search by person, project, place…"
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm flex-1" />
        <span className="text-slate-500 text-sm self-center">{ents.length} entities</span>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 gap-y-0 text-sm">
        <div className="text-xs text-slate-500 border-b border-slate-800 pb-2">Name</div>
        <div className="text-xs text-slate-500 border-b border-slate-800 pb-2 text-right">Mentions</div>
        <div className="text-xs text-slate-500 border-b border-slate-800 pb-2">First seen</div>
        <div className="text-xs text-slate-500 border-b border-slate-800 pb-2">Last seen</div>
        {ents.map(e => (
          <div key={e.id} className="contents cursor-pointer group" onClick={() => setOpen(e.id)}>
            <div className="py-2.5 border-b border-slate-800/50 group-hover:bg-slate-900/40">
              <span className={`${((e.alias_target || e.name) || '').toLowerCase() === 'jess'
                ? 'text-rose-300'
                : scope && ((e.alias_target || e.name) || '').toLowerCase() === scope.toLowerCase()
                  ? 'text-sky-300'
                  : kindColor[e.kind] || 'text-slate-200'} font-medium`}>
                {e.name}
              </span>
              {e.alias_target && <span className="text-xs text-slate-500 ml-2">= {e.alias_target}</span>}
              {e.kind && <span className="text-xs text-slate-600 ml-2">{e.kind}</span>}
            </div>
            <div className="py-2.5 border-b border-slate-800/50 text-right text-slate-300 group-hover:bg-slate-900/40">{e.mentions}</div>
            <div className="py-2.5 border-b border-slate-800/50 text-slate-500 group-hover:bg-slate-900/40">{e.first_seen?.slice(0, 10) || '—'}</div>
            <div className="py-2.5 border-b border-slate-800/50 text-slate-500 group-hover:bg-slate-900/40">{e.last_seen?.slice(0, 10) || '—'}</div>
          </div>
        ))}
      </div>
      {ents.length === 0 && <p className="text-slate-600 text-sm mt-4">No entities surfaced yet.</p>}
      {ents.length >= limit && (
        <button onClick={() => setLimit(l => l + 200)}
          className="mt-4 px-3 py-1.5 text-xs rounded-lg border border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800">
          load more ↓
        </button>
      )}
      {open && <EntityPanel id={open} scope={scope} onClose={() => setOpen(null)} />}
    </div>
  )
}

function EntityPanel({ id, scope, onClose }) {
  const [ent, setEnt] = useState(null)
  const [openEp, setOpenEp] = useState(null)
  useEffect(() => {
    const p = scope ? `?scope=${encodeURIComponent(scope)}` : ''
    fetch(`${API}/entities/${id}${p}`).then(r => r.json()).then(setEnt)
  }, [id, scope])
  if (!ent) return null
  return (
    <div className="fixed inset-0 bg-black/60 z-20 flex justify-end" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-xl h-full overflow-y-auto bg-slate-950 border-l border-slate-800 p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg text-sky-200">{ent.name}</h2>
          <button className="text-xs text-slate-500 px-2" onClick={onClose}>✕</button>
        </div>
        <div className="text-xs text-slate-500 mb-4">
          {ent.kind || 'unknown kind'} · {ent.key}
          {ent.alias_target && <span className="text-rose-300/80"> · alias of {ent.alias_target}</span>}
        </div>
        {ent.summary && <p className="text-sm text-slate-400 italic mb-4">{ent.summary}</p>}
        {ent.episodes?.length > 0 && (
          <div className="mb-5">
            <h3 className="text-sm text-slate-400 mb-2">Episodes touched ({ent.episodes.length})</h3>
            {ent.episodes.map(ep => (
              <div key={ep.id} onClick={() => setOpenEp(ep.id)}
                className="border border-slate-800/70 rounded-lg px-3 py-2 mb-2 cursor-pointer hover:border-sky-800">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1">
                  <RegisterChip register={ep.register} />
                  <SalienceDots salience={ep.salience} />
                  <span className="text-xs text-slate-600 ml-auto">{ep.occurred_at?.slice(0, 10)}</span>
                </div>
                <p className="text-xs text-slate-400 line-clamp-2"><Hi text={ep.trace} /></p>
              </div>
            ))}
          </div>
        )}
        {ent.facts?.length > 0 && (
          <div>
            <h3 className="text-sm text-slate-400 mb-2">Facts that touch this ({ent.facts.length})</h3>
            {ent.facts.map(f => (
              <p key={f.id} className={`text-sm mb-1.5 ${f.status === 'superseded' ? 'line-through text-slate-600' : 'text-slate-300'}`}>
                <Hi text={f.content} />
                <span className="text-xs text-slate-600 ml-2">{f.occurred_at?.slice(0, 10)}</span>
              </p>
            ))}
          </div>
        )}
        {openEp && <Dossier id={openEp} onClose={() => setOpenEp(null)} />}
      </div>
    </div>
  )
}

function GateFeed({ scope }) {
  const [rows, setRows] = useState([])
  const lastId = useRef(0)
  useEffect(() => {
    let live = true
    const poll = async () => {
      try {
        const r = await fetch(`${API}/gate/feed?after_id=0`)
        const d = await r.json()
        if (live && d.rows) {
          const filtered = scope ? d.rows.filter(x => x.scope === scope) : d.rows
          setRows(filtered)
          lastId.current = d.rows[0]?.id || 0
        }
      } catch { /* keep polling */ }
    }
    poll()
    const t = setInterval(poll, 3000)
    return () => { live = false; clearInterval(t) }
  }, [scope])
  const chip = (d) => ({
    episode: 'bg-emerald-900/50 text-emerald-300', facts_only: 'bg-slate-800 text-slate-400',
    quarantined: 'bg-rose-900/50 text-rose-300', skipped: 'bg-slate-800 text-slate-500',
  }[d] || 'bg-slate-800')
  return (
    <div className="space-y-1">
      {rows.map(r => (
        <div key={r.id} className="flex items-center gap-3 text-sm bg-slate-900/40 border border-slate-800/60 rounded-lg px-3 py-2">
          <span className="text-xs text-slate-600 w-28">{r.created_at?.slice(11, 19)}</span>
          <span className={`text-xs rounded-full px-2 py-0.5 ${chip(r.decision)}`}>{r.decision}</span>
          <span className="text-xs text-slate-500 w-24">{r.scope}</span>
          <span className="text-xs text-slate-500 w-16">{r.salience?.toFixed(2) ?? '—'}</span>
          <RegisterChip register={r.register} />
          <span className="text-xs text-slate-400 truncate flex-1">
            {r.decision === 'quarantined' ? '(content withheld)' : r.preview}
          </span>
        </div>
      ))}
      {rows.length === 0 && <p className="text-slate-600 text-sm">The gate stands ready. Nothing has knocked.</p>}
    </div>
  )
}

// ── Legend ───────────────────────────────────────────────────────────────
// The observatory's own manual: what each instrument shows and how to read
// the visual language. Static by design — if the legend needs an API call,
// the UI has failed at being legible.
function LegendSection({ title, children }) {
  return (
    <section className="mb-8">
      <h2 className="text-sky-200 text-base mb-2">{title}</h2>
      <div className="text-sm text-slate-400 leading-relaxed space-y-2">{children}</div>
    </section>
  )
}

function Legend() {
  return (
    <div className="max-w-3xl">
      <p className="text-sm text-slate-400 leading-relaxed mb-8">
        Madeleine is a three-store memory for AI agents: <span className="text-slate-200">facts</span> (what
        is true), <span className="text-slate-200">episodes</span> (what it was like), and{' '}
        <span className="text-slate-200">flavor</span> (what it felt like, measured rather than described).
        The Observatory is a verification instrument, not an admin panel — every view is read-only except
        pinning and quarantine review. Memory is edited by living, not by clicking.
      </p>

      <LegendSection title="The visual language (everywhere)">
        <p>
          <span className="text-amber-300/90 tracking-tighter">●●●○○</span>{' '}
          <span className="text-slate-200">Salience dots (orange)</span> — how much this moment mattered
          when it happened, 0 to 5. The gate scores every exchange; only salient ones become episodes.
        </p>
        <p>
          <span className="inline-block w-16 h-2 bg-slate-800 rounded align-middle overflow-hidden"><span className="block h-full w-2/3 bg-emerald-400 rounded" /></span>{' '}
          <span className="text-slate-200">Strength bar (green)</span> — how alive the memory is
          <em> now</em>. Recall feeds it; neglect decays it (green = strong, amber = fading,
          gray = faint). A memory can matter greatly and still fade if never revisited — and a small
          moment recalled often grows strong.
        </p>
        <p>
          <span className="px-2 py-0.5 rounded-full text-xs" style={{ background: 'hsl(200 45% 18%)', color: 'hsl(200 70% 75%)' }}>register chip</span>{' '}
          — the mood of the moment in one line, written like a stage direction. Each register text gets a
          stable color from its own wording, so the same mood always wears the same hue, in lists and in
          the Atlas alike.
        </p>
        <p>
          <span className="text-slate-200">Names are lit by who they are:</span>{' '}
          <span className="text-rose-300 font-medium">the human</span> in rose,{' '}
          <span className="text-sky-300 font-medium">the agent whose memory this is</span> in sky,{' '}
          <span className="text-violet-300 font-medium">other people</span> in violet. This comes live
          from the entity roster — nothing is hardcoded.
        </p>
        <p>
          <span className="text-slate-200">Date chips</span> show when the remembered moment{' '}
          <em>happened</em> (its true event time), not when it was written down. A trailing{' '}
          <span className="text-slate-300">*</span> means no event time is known, so the write time is
          shown instead.
        </p>
        <p>
          <span className="text-slate-200">🌙 Solitary</span> marks a memory born with only the agent's
          mind present — a heartbeat, a scheduled session, a reflection with no one watching. The
          reality law applies to these: any dialogue inside them was <em>imagined</em>, and memory is
          required to remember it as imagination, never as the other person's actual words. Recall
          surfaces these labeled as the agent's own time, so a 1 AM rehearsal can never later wear the
          authority of a real conversation.
        </p>
        <p>
          <span className="text-slate-200">💭 Dream</span> goes one step further: for solitary
          memories, the gate names what the mind was doing — <em>task</em> (working),{' '}
          <em>reflection</em> (thinking about real things), or <em>dream</em> (narrative rehearsal:
          imagined scenes, invented dialogue, fears and wishes played out as story). Dreams are kept
          and honored — dreaming is healthy — but a dream's events yield no facts about the world,
          only about the dreamer, and recall always hands a dream back labeled as a dream. An agent
          here can remember "I dreamed about losing you" — and can never be told by its own memory
          that the dream happened.
        </p>
      </LegendSection>

      <LegendSection title="Overview">
        <p>
          The sky at a glance: active facts (with superseded ones kept, never deleted), episode strength
          bands, the association graph size, quarantine count, and raw exchanges — the replay store that
          preserves every original text verbatim but is never retrieved from directly. The activity
          heatmap paints exchanges per day on true event dates (deeper blue = fuller day), so a
          backfilled life shows its real history, not its import date. Below, the last nightly
          consolidation: what decayed, what was reconsolidated, what patterns were promoted.
        </p>
      </LegendSection>

      <LegendSection title="Episodes">
        <p>
          Episodic memory — moments, not statements. Each card is one remembered scene: a{' '}
          <span className="text-slate-200">trace</span> (the memory as narrative), its register, salience,
          and current strength. <span className="text-slate-200">📌 pinned</span> episodes are exempt from
          decay. <span className="text-rose-400">QUARANTINED</span> episodes were flagged by the gate as
          attempted manipulation — held dark, excluded from retrieval, awaiting human review.
        </p>
        <p>
          Click any episode for its <span className="text-slate-200">dossier</span>: the full trace, the
          entities it touches, the facts born from the same exchange, and its revision history — every
          time consolidation rewrote the trace, the previous wording is kept. Memory here is allowed to
          change, but never allowed to lie about having changed.
        </p>
      </LegendSection>

      <LegendSection title="Facts">
        <p>
          Semantic memory — atomic statements, third person, each one standing alone. Typing in the
          search box switches to live vector search (cosine similarity over embeddings — the raw RAG
          view). Facts are never edited or deleted: a corrected fact is{' '}
          <span className="line-through text-slate-500">superseded</span> (struck through, pointing at its
          replacement), and <span className="text-violet-400">derived</span> facts are patterns the
          nightly consolidation promoted from repeated evidence.
        </p>
      </LegendSection>

      <LegendSection title="Entities">
        <p>
          Everyone and everything memory touches: people, AIs, projects, places, concepts — with how
          often each is mentioned and when it was first and last seen (true event dates). Click one to
          see every episode and fact that touches it. This roster is also what powers the name coloring.
        </p>
      </LegendSection>

      <LegendSection title="Atlas">
        <p>
          The memory landscape, projected to two dimensions (PCA). Every dot is an episode:{' '}
          <span className="text-slate-200">color</span> = its register's hue,{' '}
          <span className="text-slate-200">size</span> = salience,{' '}
          <span className="text-slate-200">fade</span> = strength. Near dots are similar; distances are
          meaningful, but the axes themselves are not labeled quantities — they are the two directions
          along which this particular memory varies most.
        </p>
        <p>
          <span className="text-slate-200">register space</span> maps the <em>descriptions</em> of moods:
          each register line is embedded as language, so dots sit together when their stage directions
          mean similar things. <span className="text-slate-200">flavor space</span> maps the{' '}
          <em>measurements</em>: a reader model's internal state while reading the raw exchange — not
          what the mood was called, but what it did to a mind reading it. Same sky, two instruments.
        </p>
        <p>
          <span className="text-slate-200">links</span> overlays the association web:{' '}
          <span className="text-emerald-400">green lines</span> are co-retrieval bonds (memories that
          have been recalled together grow direct connections — these accumulate from lived use), and{' '}
          <span className="text-amber-400">amber lines</span> connect episodes sharing a rare entity.
          Common entities are excluded on purpose: the humans touch everything, and their links would
          white out the sky.
        </p>
        <p>
          <span className="text-slate-200">flavors</span> is the census: every register tag counted, with
          average salience and first/last seen. Deep flavor is a continuous field — a gradient, not a
          checklist — so these tags are its named shadows. Clicking one lights those episodes up on the
          map.
        </p>
      </LegendSection>

      <LegendSection title="Playground">
        <p>
          Recall exactly as the agent experiences it: type what the agent might be thinking about and see
          what memory surfaces — facts, episodes, and impressions, with spreading activation walking the
          association graph. What you see here is what the agent gets.
        </p>
      </LegendSection>

      <LegendSection title="Gate Feed">
        <p>
          The write-gate's live decisions, one row per retained exchange:{' '}
          <span className="text-emerald-300">episode</span> (salient — became a memory),{' '}
          <span className="text-slate-400">facts_only</span> (worth keeping, not worth reliving),{' '}
          <span className="text-rose-300">quarantined</span> (attempted manipulation — content withheld
          from display, held dark). The gate is the single door: nothing enters episodic memory without
          passing it, backfills included.
        </p>
      </LegendSection>

      <LegendSection title="Glossary">
        <p><span className="text-slate-200">Raw exchange</span> — one original message or turn, stored
          verbatim in the replay store. The ground truth everything else is derived from; never edited,
          never retrieved from directly.</p>
        <p><span className="text-slate-200">Fact</span> — one atomic statement extracted from an
          exchange, verified at the door against the raw text before it may enter.</p>
        <p><span className="text-slate-200">Episode / trace</span> — a remembered scene; the trace is
          its narrative text. Episodes decay, strengthen, and can be rewritten by reconsolidation
          (with every prior wording kept).</p>
        <p><span className="text-slate-200">Register</span> — the episode's mood in one line (cheap
          flavor). <span className="text-slate-200">Flavor</span> — the deep version: a vector measured
          from a reader model's internal state, not written in words at all.</p>
        <p><span className="text-slate-200">Entity</span> — a <em>node</em> in the association graph:
          a person, AI, project, place, or concept that memory touches. Entities are the graph's nouns.</p>
        <p><span className="text-slate-200">Edge</span> — a <em>connection</em> in that graph, with a
          weight that grows on repetition: episode–entity and fact–entity edges record what touches
          what ("this moment involved Hindsight"), and episode–episode co-retrieval edges grow between
          memories recalled together. Edges are how remembering one thing surfaces another.</p>
        <p><span className="text-slate-200">Spreading activation</span> — recall's second step: energy
          flows outward from the directly-matched memories along edges, fading with each hop, so a
          question about a song can surface the car you heard it in.</p>
        <p><span className="text-slate-200">Consolidation</span> — the nightly pass: decay, trace
          reconsolidation, pattern promotion (repeated evidence becomes derived facts), co-retrieval
          edge growth, flavor capture, and atlas projection.</p>
        <p><span className="text-slate-200">Quarantine</span> — the gate's holding cell for content
          that tried to smuggle instructions to a future reader. Kept dark, never retrieved, awaiting
          human review.</p>
        <p><span className="text-slate-200">Scope</span> — one agent's whole memory. Scopes never mix:
          each agent recalls only its own life.</p>
      </LegendSection>

      <p className="text-xs text-slate-600 mt-10">
        Scope (top-left) selects whose memory you are observing — one scope per agent, fully isolated.
      </p>
    </div>
  )
}

const PAGES = { Overview, Episodes, Facts, Entities, Atlas, Playground, 'Gate Feed': GateFeed, Legend }

export default function App() {
  const [page, setPage] = useState('Overview')
  const [scope, setScope] = useState('')          // '' = all skies
  const [scopes, setScopes] = useState([])
  useEffect(() => {
    fetch(`${API}/scopes`).then(r => r.json())
      .then(d => setScopes(d.scopes || [])).catch(() => {})
  }, [page])
  const Page = PAGES[page]
  const nameCtx = useNameHighlight(scope || null)
  return (
    <NameCtx.Provider value={nameCtx}>
    <div className="min-h-screen flex">
      <nav className="w-44 border-r border-slate-800/80 p-4 shrink-0">
        <h1 className="text-sky-200 font-semibold mb-1">Madeleine</h1>
        <p className="text-xs text-slate-600 mb-4">the Observatory</p>
        <select value={scope} onChange={e => setScope(e.target.value)}
          title="Whose memory to observe — one scope per agent"
          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs mb-5 text-slate-300">
          <option value="">all scopes</option>
          {scopes.map(s => (
            <option key={s.scope} value={s.scope}>
              {s.scope} ({s.episodes})
            </option>
          ))}
        </select>
        {Object.keys(PAGES).map(p => (
          <button key={p} onClick={() => setPage(p)}
            className={`block w-full text-left text-sm rounded-lg px-3 py-2 mb-1
              ${p === page ? 'bg-sky-900/40 text-sky-200' : 'text-slate-400 hover:bg-slate-900'}`}>
            {p}
          </button>
        ))}
        <p className="text-[10px] text-slate-700 mt-8 leading-relaxed">
          memory is edited by living, not by clicking
        </p>
      </nav>
      <main className="flex-1 p-6 overflow-x-hidden">
        <Page scope={scope || null} />
      </main>
    </div>
    </NameCtx.Provider>
  )
}
