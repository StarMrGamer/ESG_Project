import { useStore } from '../../store'
import { Spinner } from '../ui'
import FiltersRail from './FiltersRail'
import CenterBoard from './CenterBoard'
import AssistantRail from './AssistantRail'
import AssistantBar from './AssistantBar'
import EngineBoard from './EngineBoard'
import PPPBanner from '../dual/PPPBanner'
import UniverseGrid from './UniverseGrid'
import ResidualPanel from '../dual/ResidualPanel'
import RoadmapPanel from '../dual/RoadmapPanel'
import PPPPanel from '../dual/PPPPanel'
import ContextTab from './ContextTab'
import ClientsTab from '../clients/ClientsTab'
import Manual from '../manual/Manual'
import { SHOW_CLIENTS } from '../../features'
import { MODULES, isNative, isPinned, showModule } from '../../lib/modules'
import type { ModuleKey } from '../../store'

/**
 * The board, layered.
 *
 * Every block below declares the level it earns. Nothing above the current level renders, and
 * the step-up bar at the foot says what the next level would add — so depth is something the
 * user walks into, not something they arrive inside.
 *
 * The disagreement matrix is deliberately last to appear. It is the most information-dense thing
 * on the page and it used to be the first thing on it, which is most of why the board read as
 * overwhelming: a wall of dots before you knew what a dot meant.
 */

const NEXT: Record<number, string> = {
  1: 'Every panel at once: the disagreement matrix, the risk tiers, the universe grid, the '
    + 'evidence trail and the run provenance.',
}
/**
 * The foot of the board: step up a whole level, or pin one module onto the level you are on.
 *
 * Both are offered together on purpose. The level is the right default and most people should
 * take it; the chips are for the reader who wants exactly one more thing — usually the matrix —
 * and should not have to accept eight panels to get it.
 */
function ModuleBar() {
  const { settings, setSettings } = useStore()
  const lv = settings.level
  const next = lv === 1 ? (3 as const) : null

  const toggle = (key: ModuleKey) => {
    const on = settings.extras.includes(key)
    const extras = on ? settings.extras.filter(k => k !== key) : [...settings.extras, key]
    // Pinning the rails has to OPEN them too, or the module is on and nothing appears: at
    // Preferences both rails are closed, and `leftOpen`/`rightOpen` are what actually draw them.
    // Unpinning closes them for the same reason in reverse — the chip and the header's own two
    // rail buttons must never end up saying different things about what is on screen.
    setSettings(key === 'rails'
      ? { extras, leftOpen: !on, rightOpen: !on }
      : { extras })
  }

  // ONE list, in registry order, whatever is on. Splitting it into pinned-then-off meant the
  // chip you just clicked jumped to the front of the row and everything shuffled under your
  // cursor — so the second chip you reached for was no longer where you were looking. A toggle
  // that moves when you use it is a toggle you have to re-find every time.
  const offerable = MODULES.filter(m => !isNative(m.key, settings))
  if (!next && !offerable.length) return null

  return (
    <div className="step-up">
      <div className="step-up-main">
        {next && (
          <div className="step-up-row">
            <div>
              <div className="step-up-h">There is more underneath</div>
              <div className="cc-muted">{NEXT[lv]}</div>
            </div>
            <button className="btn btn-primary"
              onClick={() => setSettings({ level: next, leftOpen: true, rightOpen: true })}>
              Show everything →
            </button>
          </div>
        )}
        {offerable.length > 0 && (
          <div className="step-up-add" data-tour="add-modules">
            <span className="step-up-label">
              {next ? 'Or add just the parts you want' : 'Pinned to this level'}
            </span>
            <div className="step-up-chips">
              {offerable.map(m => {
                const on = isPinned(m.key, settings)
                return (
                  <button key={m.key} aria-pressed={on} title={m.blurb}
                    className={`cc-chip step-up-chip ${on ? 'is-on' : ''}`}
                    onClick={() => toggle(m.key)}>
                    <span className="step-up-sign" aria-hidden>{on ? '×' : '+'}</span> {m.label}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { board, boardLoading, boardError, settings } = useStore()
  const lv = settings.level
  // Rails are level-2 furniture. At level 1 the centre column runs full width whatever the
  // toggles say, so "Brief" is genuinely brief rather than brief-plus-two-sidebars.
  const rails = showModule('rails', settings)
  const lo = rails && settings.leftOpen
  const ro = rails && settings.rightOpen
  const cls = lo && ro ? 'both' : lo ? 'left-only' : ro ? 'right-only' : 'neither'


  return (
    <div>
      {boardError && <div className="error-note">Couldn't load the board: {boardError}</div>}
      {!board && boardLoading && <Spinner label="Loading the command center…" />}
      {board && (
        <>
          {/* A browser that stored `tab: 'clients'` before the flag went off must not
              open on a tab it can no longer navigate away from by name. */}
          {settings.tab === 'manual'
            ? <Manual />
            : SHOW_CLIENTS && settings.tab === 'clients'
            ? <ClientsTab />
            : settings.tab === 'context'
            ? <ContextTab />
            : (
              <>
                {/* The lens the setup asked for, and what it is currently doing to the board.
                    Above the matrix and above the level gate on purpose: it is a control, not a
                    panel, and a preference whose effect you cannot see is not a preference. */}
                <PPPBanner />
                {showModule('matrix', settings) && <EngineBoard />}
                {/* The one-line assistant is what level 1 has INSTEAD of the rail. With the
                    rail pinned on, showing both would be the same assistant twice. */}
                {lv === 1 && !ro && <AssistantBar />}
                <div className={`dash-grid ${cls}`}>
                  {lo && <div><FiltersRail /></div>}
                  <div><CenterBoard /></div>
                  {ro && <div><AssistantRail /></div>}
                </div>
                {/* Per-company, so it stays with the company content — above the cohort
                    panels, and full width, which is what the ternary plot needs. */}
                {showModule('triangle', settings) && <PPPPanel />}
                {showModule('universe', settings) && <UniverseGrid />}
                {/* Cohort-level, so it sits under the grid rather than in the company column —
                    it is a statement about the whole panel, not about the focused name. */}
                {showModule('residual', settings) && <ResidualPanel />}
                {/* Forward-looking, so it sits AFTER the measured panels — a reader should meet
                    what we can show before what we would like to show. */}
                {showModule('roadmap', settings) && <RoadmapPanel />}
                <ModuleBar />
              </>
            )}
        </>
      )}
    </div>
  )
}
