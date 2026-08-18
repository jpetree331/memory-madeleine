// Madeleine — the Observatory. Not an admin panel: every view is a
// verification instrument. Read-only by design except pin + quarantine
// review ("memory is edited by living, not by clicking").
import { useCallback, useEffect, useRef, useState } from 'react'

const API = '/api'

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
      {t.slice(0, 10)}{!occurred && '*'}
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

const SalienceDots = ({ salience }) => (
  <span className="tracking-tighter text-amber-300/90" title={`salience ${salience?.toFixed(2)}`}>
    {'●'.repeat(Math.round((salience || 0) * 5)).padEnd(5, '○')}
  </span>
)

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
          {ep.quarantined && <span className="text-rose-400 text-xs">QUARANTINED</span>}
        </div>
        <p className="text-slate-200 leading-relaxed mb-4">{ep.trace}</p>
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
                {f.content} {f.kind === 'derived' && <span className="text-violet-400 text-xs">derived</span>}
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
  const [open, setOpen] = useState(null)
  useEffect(() => {
    const t = setTimeout(() =>
      fetch(`${API}/episodes?sort=${sort}${q ? `&q=${encodeURIComponent(q)}` : ''}` +
            (scope ? `&scope=${encodeURIComponent(scope)}` : ''))
        .then(r => r.json()).then(setData), 200)
    return () => clearTimeout(t)
  }, [q, sort, scope])
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
              {ep.pinned && <span title="pinned">📌</span>}
              {ep.quarantined && <span className="text-rose-400 text-xs">QUARANTINED</span>}
              <span className="text-xs text-slate-600 ml-auto flex items-center gap-3">
                <WhenChip occurred={ep.occurred_at} created={ep.created_at} />
                <span>recalls {ep.recall_count}</span>
              </span>
            </div>
            <p className="text-sm text-slate-300 line-clamp-2">{ep.trace}</p>
          </div>
        ))}
        {data.episodes.length === 0 && (
          <p className="text-slate-600 text-sm">No episodes yet — memory is waiting to live a little.</p>
        )}
      </div>
      {open && <Dossier id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function Facts({ scope }) {
  const [data, setData] = useState({ facts: [], total: 0, mode: 'list' })
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('created_at')
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams()
      if (scope) p.set('scope', scope)
      if (q.trim()) p.set('q', q.trim())
      if (status) p.set('status', status)
      if (sort) p.set('sort', sort)
      fetch(`${API}/facts?${p}`).then(r => r.json()).then(setData)
    }, 300)
    return () => clearTimeout(t)
  }, [q, scope, status, sort])
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
              {f.content}
            </span>
            <span className="text-xs text-slate-600 ml-2">
              {(f.occurred_at || f.created_at) && (
                <span className="text-slate-500 mr-2"
                  title={f.occurred_at ? `occurred ${f.occurred_at}` : `retained ${f.created_at} (no event date)`}>
                  {(f.occurred_at || f.created_at).slice(0, 10)}{!f.occurred_at && '*'}
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
  const [hover, setHover] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => {
    const p = new URLSearchParams({ space })
    if (scope) p.set('scope', scope)
    fetch(`${API}/atlas?${p}`).then(r => r.json())
      .then(d => setPoints(d.points || [])).catch(() => setPoints([]))
  }, [space, scope])
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const pad = 0.08
  const x0 = Math.min(...xs), x1 = Math.max(...xs)
  const y0 = Math.min(...ys), y1 = Math.max(...ys)
  const sx = x => 60 + ((x - x0) / ((x1 - x0) || 1)) * 680 * (1 - pad)
  const sy = y => 40 + ((y - y0) / ((y1 - y0) || 1)) * 440 * (1 - pad)
  return (
    <div>
      <div className="flex items-center gap-4 mb-3">
        <div className="flex rounded-lg overflow-hidden border border-slate-800">
          {['register', 'flavor'].map(s => (
            <button key={s} onClick={() => setSpace(s)}
              className={`px-3 py-1.5 text-xs ${space === s ? 'bg-sky-900/60 text-sky-200' : 'bg-slate-900 text-slate-500'}`}>
              {s} space
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-500">
          {points.length} episodes · color = register · size = salience · fade = strength
        </span>
        {space === 'flavor' && points.length === 0 && (
          <span className="text-xs text-amber-400">
            no flavor projections yet — the reader captures in the nightly window
          </span>
        )}
      </div>
      <svg viewBox="0 0 760 500" className="w-full bg-slate-950/60 border border-slate-800 rounded-xl">
        {points.map(p => (
          <circle key={p.id} cx={sx(p.x)} cy={sy(p.y)}
            r={3 + (p.salience || 0.5) * 7}
            fill={`hsl(${hue(p.register || '')} 65% 60%)`}
            opacity={Math.max(0.25, Math.min(0.95, p.strength || 1))}
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
      {open && <Dossier id={open} onClose={() => setOpen(null)} />}
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

const PAGES = { Overview, Episodes, Facts, Atlas, Playground, 'Gate Feed': GateFeed }

export default function App() {
  const [page, setPage] = useState('Overview')
  const [scope, setScope] = useState('')          // '' = all skies
  const [scopes, setScopes] = useState([])
  useEffect(() => {
    fetch(`${API}/scopes`).then(r => r.json())
      .then(d => setScopes(d.scopes || [])).catch(() => {})
  }, [page])
  const Page = PAGES[page]
  return (
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
  )
}
