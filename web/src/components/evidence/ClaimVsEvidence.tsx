/**
 * ClaimVsEvidence — what a company SAYS, against what an independent source can see.
 *
 * Prototype_Build_Notes.md §6. Three rows, one collapsible panel, and the word ILLUSTRATIVE is
 * non-negotiable: no satellite query runs here.
 *
 * The design decision that matters is that "illustrative" is drawn PER SIDE and PER VERDICT
 * rather than once at the top. A blanket disclaimer over a panel where one row is a real
 * determination teaches the reader to discount all three — and the real one is the best row in
 * the set, because it is the tool saying "no independent dataset exists, we do not know."
 * So every claim, every piece of evidence and every verdict carries `checked`, and an unchecked
 * verdict is drawn hollow with its reason attached.
 */
import { useEffect, useState } from 'react'
import { api } from '../../api'
import type { ClaimEvidencePayload } from '../../types'

const VERDICT_LABEL: Record<string, string> = {
  corroborated: 'Corroborated',
  partial: 'Partial',
  not_corroborated: 'Not corroborated',
  no_independent_data: 'No independent data',
}

export default function ClaimVsEvidence({ ticker }: { ticker?: string }) {
  const [data, setData] = useState<ClaimEvidencePayload | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    api.claimEvidence(ticker).then(d => { if (alive) setData(d) }).catch(() => {})
    return () => { alive = false }
  }, [ticker])

  if (!data?.available || !data.rows.length) return null

  return (
    <div className="cve">
      <button className="cve-head" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span className="cve-title">Claim vs Evidence</span>
        <span className="cve-illus">illustrative</span>
        <span className="cve-caret">{open ? '−' : '+'}</span>
      </button>
      <p className="cve-sub">{data.header}</p>

      {open && (
        <div className="cve-rows">
          {data.rows.map(row => (
            <div className="cve-row" key={row.company_id}>
              <div className="cve-co">
                <b>{row.company}</b>
                <span className="cve-co-id">{row.company_id}</span>
                <span className="cve-why">{row.why_this_one}</span>
              </div>

              <div className="cve-grid">
                <div className="cve-side">
                  <div className="cve-side-h">Claim</div>
                  <div className="cve-text">{row.claim.text}</div>
                  <div className="cve-src">
                    {row.claim.source_url
                      ? <a href={row.claim.source_url} target="_blank" rel="noreferrer">
                          {row.claim.source}</a>
                      : row.claim.source}
                    {row.claim.date ? ` · ${row.claim.date}` : ''}
                    <span className={`cve-flag ${row.claim.checked ? 'on' : 'off'}`}>
                      {row.claim.checked ? 'checked' : 'not run'}
                    </span>
                  </div>
                  <div className="cve-basis">{row.claim.basis}</div>
                </div>

                <div className="cve-arrow" aria-hidden>→</div>

                <div className="cve-side">
                  <div className="cve-side-h">Independent evidence</div>
                  <div className="cve-text">{row.evidence.text}</div>
                  <div className="cve-src">
                    {row.evidence.source_url
                      ? <a href={row.evidence.source_url} target="_blank" rel="noreferrer">
                          {row.evidence.source}</a>
                      : row.evidence.source}
                    {row.evidence.date ? ` · ${row.evidence.date}` : ''}
                    <span className={`cve-flag ${row.evidence.checked ? 'on' : 'off'}`}>
                      {row.evidence.checked ? 'checked' : 'not run'}
                    </span>
                  </div>
                  <div className="cve-basis">{row.evidence.basis}</div>
                </div>
              </div>

              <div className="cve-verdict-line">
                <span className={`cve-verdict ${row.verdict}${row.verdict_checked ? '' : ' hollow'}`}>
                  {VERDICT_LABEL[row.verdict] || row.verdict}
                </span>
                <span className="cve-verdict-note">
                  {row.verdict_checked ? '' : 'Illustrative outcome — '}{row.verdict_note}
                </span>
              </div>
            </div>
          ))}

          <p className="cve-foot">{data.deck_line}</p>
        </div>
      )}
    </div>
  )
}
