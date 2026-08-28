import { useEffect, useState } from 'react'
import { useStore } from '../../store'
import { buildRecap, recapMarkdown, type RecapFacts } from './recap'

/**
 * The closing card of the recap track — everything the walk passed, in one block.
 *
 * It is assembled when the card opens, not when the tour started: the walk clicks Verify on the
 * way past, so the anchor status here is the one that check produced rather than a guess made
 * five steps earlier.
 *
 * WHAT IT REFUSES TO DO. It does not rank, score, recommend, or round a figure up. `unknown`
 * financials render as unknown rather than as a failure — the same discipline `traction.py` and
 * `financials.py` keep, and the reason the number beside it can be trusted. And every copy
 * carries the run id, because a consolidated block with no provenance is a set of numbers that
 * will outlive the run that produced them.
 */

const pct = (n: number) => `${Math.round(n * 100)}`
const signed = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}`
const FIN_TONE: Record<string, string> = {
  strong: 'cc-pos', adequate: 'cc-flat', weak: 'cc-neg', unknown: 'cc-flat',
}

export default function RecapCard({ ticker }: { ticker: string }) {
  const { board, settings, toast } = useStore()
  const [facts, setFacts] = useState<RecapFacts | null>(null)
  const [failed, setFailed] = useState(false)
  /** Revealed only when the clipboard refuses — see `copy`. */
  const [raw, setRaw] = useState('')

  useEffect(() => {
    let dead = false
    void buildRecap(board, ticker, settings.demo, settings.horizon)
      .then(f => { if (!dead) { setFacts(f); setFailed(!f) } })
      .catch(() => { if (!dead) setFailed(true) })
    return () => { dead = true }
  }, [board, ticker, settings.demo, settings.horizon])

  /**
   * Copy, and MEAN it.
   *
   * `navigator.clipboard.writeText` does not reject when the document has lost focus — Chrome
   * leaves the promise pending until the page is focused again, which on a presenting machine
   * (second display, a click that landed on the other window) is a button that silently does
   * nothing at the exact moment someone is waiting for the text. So the write is raced against a
   * short deadline, and a miss reveals the Markdown in a selectable block instead of a shrug.
   */
  const copy = async () => {
    if (!facts) return
    const md = recapMarkdown(facts)
    const wrote = await Promise.race([
      navigator.clipboard?.writeText(md).then(() => true).catch(() => false)
        ?? Promise.resolve(false),
      new Promise<boolean>(r => window.setTimeout(() => r(false), 1200)),
    ])
    if (wrote) { setRaw(''); toast('Recap copied as Markdown.', 'good'); return }
    setRaw(md)
    toast('The browser would not take the clipboard — the text is below, select and copy.', 'info')
  }

  /** Always available, and the one that survives a locked-down browser: a real file. */
  const download = () => {
    if (!facts) return
    const url = URL.createObjectURL(new Blob([recapMarkdown(facts)], { type: 'text/markdown' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `recap-${facts.runId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (failed) {
    return (
      <div className="recap-card">
        <div className="recap-head"><span className="recap-title">Nothing to consolidate</span></div>
        <p className="cc-muted">
          This run has no engine block loaded, so there are no figures to gather. Load the board
          and run the recap again.
        </p>
      </div>
    )
  }
  if (!facts) return <div className="recap-card"><span className="cc-muted">Gathering the run…</span></div>

  const c = facts.company
  return (
    <div className="recap-card">
      <div className="recap-head">
        <span className="recap-title">This run, consolidated</span>
        <span className="recap-run">
          run <b>{facts.runId}</b> · as of {facts.asOf} · {facts.horizon} · {facts.halfLifeDays}d half-life
        </span>
        {facts.demo && <span className="cc-tag-illus">illustrative demo universe</span>}
        <button className="btn recap-download" onClick={download}
          title="Save the same block as a .md file, named for the run.">Download .md</button>
        <button className="btn btn-primary recap-copy" onClick={() => void copy()}>
          Copy as Markdown
        </button>
      </div>

      <div className="recap-grid">
        <div className="recap-col">
          <div className="recap-k">Where the run stands</div>
          <dl className="recap-dl">
            {Object.entries(facts.labelCounts).map(([k, n]) => (
              <div key={k}><dt>{facts.labelNames[k] ?? k}</dt><dd>{n}</dd></div>
            ))}
          </dl>
          <dl className="recap-dl is-nmk">
            <div><dt>Issuers priced in (N)</dt><dd>{facts.nmk.N}</dd></div>
            <div><dt>Bond-ready pipeline (M)</dt><dd>{facts.nmk.M}</dd></div>
            <div><dt>Review list (K)</dt><dd>{facts.nmk.K}</dd></div>
          </dl>
        </div>

        <div className="recap-col">
          {c ? (
            <>
              <div className="recap-k">{c.name}</div>
              <div className="recap-verdict">
                <span className="recap-label">{c.label}</span>
                <span className="recap-gap">{signed(c.disagreement)}</span>
                <span className="cc-muted">
                  confidence {c.confidence.toFixed(2)} · {c.signals} dated signals
                </span>
              </div>
              <p className="recap-line">
                The rating puts it at the <b>{pct(c.ratingPct)}th</b> percentile; our evidence at
                the <b>{pct(c.evidencePct)}th</b>.
                {c.notch && <> Basket notch <b>{c.notch}</b> — unattributed, display only.</>}
              </p>
              <p className="recap-line">
                Financial read <b className={FIN_TONE[c.financial] ?? ''}>{c.financial}</b> —
                reported beside the ESG verdict, never merged into it.
              </p>
              {c.loadBearing !== null && (
                <p className="recap-line">
                  <b>{c.loadBearing}</b> of {c.signals} signals would move the label on their own
                  {c.flipSet ? <>; the <b>{c.flipSet}</b> heaviest would all have to go.</> : '.'}
                </p>
              )}
              {c.watchOuts.length > 0 && (
                <ul className="recap-watch">
                  {c.watchOuts.slice(0, 3).map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </>
          ) : (
            <>
              <div className="recap-k">No company focused</div>
              <p className="cc-muted">
                The run-level figures are on the left. Focus a company and run the recap again to
                consolidate its verdict too.
              </p>
            </>
          )}
          {facts.anchor && (
            <p className="recap-line recap-anchor">
              Merkle root over {facts.anchor.leaves} leaves — <b>{facts.anchor.status}</b>
              {facts.anchor.chain ? ` on ${facts.anchor.chain}` : ''}.
            </p>
          )}
        </div>
      </div>

      {raw && (
        <textarea className="recap-raw" readOnly value={raw} spellCheck={false}
          onFocus={e => e.currentTarget.select()} />
      )}

      <div className="recap-foot">
        <b>disagreement</b> = our evidence percentile − the incumbent rating's, inside this run's
        cohort. The baseline rating is a MOCK stand-in for the licensed figure. Never buy / sell /
        hold — not investment advice.
      </div>
    </div>
  )
}
