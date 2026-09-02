/**
 * record_demo_reel.mjs — stage 1 of the 3-minute pitch demo video: the FOOTAGE.
 *
 *   python server.py                     # the app has to be up; this drives the real thing
 *   node scripts/record_demo_reel.mjs    # -> docs/pitch/video/reel/assets/ch1..ch4.mp4
 *   cd docs/pitch/video/reel && npx hyperframes render \
 *       --quality high --video-frame-format png --fps 30    # stage 2: slates + camera
 *
 * Stage 2's `--video-frame-format png` is not optional for this project: the default `auto`
 * extracts source frames as JPEG, and JPEG ringing on a dark UI full of 1px rules and 11px
 * monospace is visible at slide size. The finished chapters are then cut out of the rendered
 * master at 0 / 42 / 84 / 136 — the same boundaries CHAPTERS declares below.
 *
 * Two takes. Take A drives the app's own **Why it matters** track (`?fears=1`) for chapters 1-3;
 * take B walks the Context tab for chapter 4. Everything is the REAL basket, Demo OFF, on
 * whatever run the server has frozen — the script never fabricates a screen.
 *
 * A SECOND REEL LIVES IN THE SAME RIG:
 *
 *   node scripts/record_demo_reel.mjs --analyst   # -> docs/pitch/video/analyst/assets/ch1..ch5.mp4
 *
 * That one drives the **Solving for the 10%** track (`?analyst=1`) — the workflow of the reader
 * this was built for, ending on the two-stage residual test. It is a second LIST OF HOLDS and a
 * second chapter table, not a second rig: the sync-frame convention, the hidden bar, the cut
 * path and the encoder settings are shared, so a fix to any of them fixes both reels. Adding a
 * parallel script is how two recorders drift until only one of them still produces usable
 * footage.
 *
 * IT REQUIRES A SERVER RUNNING THE CURRENT CODE. The residual panel is served off
 * `engine.residual`, so a long-lived `server.py` started before that existed will record a
 * chapter 04 with nothing in it. Restart the app, or point ESG_APP_URL at a fresh instance.
 *
 * THREE THINGS HERE ARE LOAD-BEARING, and each one cost a rebuild to learn:
 *
 * 1. THE PRESENT BAR IS HIDDEN WITH `opacity: 0`, NEVER `display: none`. `lib/anchor` reserves
 *    the bar's height as the CONSTANT `PRESENT_BAR_H`, not by measuring the DOM, so the ring
 *    positions itself against a band it assumes is there. Hiding the bar any other way leaves the
 *    ring correct and the layout shifted, or vice versa; making it transparent changes nothing at
 *    all about the measurement, which is the point.
 *
 * 2. PAGE ZOOM IS NOT AN OPTION for making the text bigger. `document.documentElement.style.zoom`
 *    does enlarge the UI, and it desynchronises `getBoundingClientRect` from what is painted, so
 *    every highlight ring lands somewhere near but not on its subject. The capture is native
 *    1920x1080 and legibility is bought with the camera in the composition instead.
 *
 * 3. THE CUT POINTS COME FROM THE PICTURE, NOT FROM THIS SCRIPT'S CLOCK. Chromium's screencast
 *    starts before the page settles and keeps writing after the last action, so the wall-clock
 *    time of a keypress here is up to four seconds adrift from the frame it produced. The first
 *    build trusted the clock and put Adaro's chart under Sembcorp's camera move. So each take
 *    opens on a solid MAGENTA SYNC FRAME: one full-frame colour nothing in the app can imitate,
 *    removed exactly at t=0, and every cut below is measured from that frame. It is found by the
 *    marker's COLOUR, not by scene detection — see `syncPoint`, and read that note before
 *    changing it, because the obvious implementation is off by the settle duration.
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, rmSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = await import(join(ROOT, 'web/node_modules/playwright/index.mjs'))

const APP = process.env.ESG_APP_URL || 'http://localhost:8000'

/* Which reel to shoot. The default is unchanged, so every existing invocation and every
   composition pointing at `reel/assets` keeps working untouched. */
const ANALYST = process.argv.includes('--analyst')
const REEL = ANALYST ? 'analyst' : 'reel'

/* The cut clips land where the composition's <video src> already points, so stage 2 is a
   render and never a re-wiring. Both directories are intermediates — git-ignored, rebuildable. */
const OUT = join(ROOT, `docs/pitch/video/${REEL}/assets`)
const RAW = join(ROOT, `docs/pitch/video/${REEL}/raw`)

/* Analyst view, level 3, dark, Demo OFF. The track sets most of this itself in its first step,
   but a browser that has never met the app would otherwise open on setup instead of the board. */
const SETTINGS = {
  demo: false, dark: true, simplified: false, level: 3, setupDone: true, tourDone: true,
  tourDeck: '', extras: [], focus: '', ppp: 'balanced',
  profile: { mandate: 'risk', goal: 'screen', label: 'protect the downside across ASEAN' },
  filters: { country: 'All', sector: 'All' }, leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', horizon: 'long', pipelineOnly: false,
}

const SYNC = `<div id="__sync" style="position:fixed;inset:0;z-index:2147483647;background:#ff00c8"></div>`
const HIDE_BAR = `.present-bar{opacity:0!important;pointer-events:none!important}`

const sh = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`${cmd} failed: ${r.stderr?.slice(0, 800)}`)
  return r.stdout + r.stderr
}

/**
 * t=0 is the first frame AFTER the magenta marker — found by the marker's own COLOUR.
 *
 * This used to be `select='gt(scene,0.5)'` taking the first hit, on the belief that a take holds
 * exactly one full-frame transition. It holds TWO: the app is already painted when the marker is
 * inserted, so magenta APPEARING is a scene change of its own, and it is the earlier one. Every
 * cut therefore landed one settle-duration late — measured on take C, 2.28 vs the true 7.28, a
 * five-second shift that put chapter 05 on chapter 04's panel and opened chapter 01 on a solid
 * magenta frame. Takes A and B were shifted by their own settles (4s and 2s) in the same way.
 *
 * Colour is the right discriminator because the marker was chosen to be one no UI can imitate.
 * #ff00c8 sits at the far edge of the V (red-difference) chroma plane, around 255 against ~125
 * for the dark board, so "V is enormous" identifies the marker and nothing else. The scan is
 * capped at the first 30 seconds: the marker is always in the opening beat, and signalstats over
 * a three-minute capture is needlessly slow.
 */
const MAGENTA_V = 200

const syncPoint = file => {
  const out = sh('ffmpeg', ['-v', 'error', '-i', file, '-t', '30', '-vf',
    'scale=32:18,signalstats,metadata=print:file=-', '-an', '-f', 'null', '-'])
  let t = null, seenMarker = false
  for (const line of out.split('\n')) {
    const pts = line.match(/pts_time:([0-9.]+)/)
    if (pts) { t = parseFloat(pts[1]); continue }
    const v = line.match(/VAVG=([0-9.]+)/)
    if (!v || t === null) continue
    if (parseFloat(v[1]) > MAGENTA_V) seenMarker = true
    else if (seenMarker) return t          // first frame after the marker is removed
  }
  throw new Error(`no magenta marker found in ${file} — was it painted, and did it come down?`)
}

const only = dir => join(dir, readdirSync(dir).find(f => f.endsWith('.webm')))

async function open(browser, dir) {
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir, size: { width: 1920, height: 1080 } },
  })
  const page = await ctx.newPage()
  await page.addInitScript(s => localStorage.setItem('esg-radar-settings', JSON.stringify(s)), SETTINGS)
  return { ctx, page }
}

/** Paint the marker, let the board settle behind it, then drop it: that is t=0. */
async function sync(page, settleMs) {
  await page.evaluate(html => document.body.insertAdjacentHTML('beforeend', html), SYNC)
  await page.waitForTimeout(settleMs)
  await page.evaluate(() => document.getElementById('__sync')?.remove())
}

const wait = (page, s) => page.waitForTimeout(s * 1000)

// ── take A · chapters 1-3, driven through the app's own Why it matters track ────────────
async function takeA(browser) {
  const { ctx, page } = await open(browser, join(RAW, 'A'))
  await page.goto(`${APP}/?fears=1`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.addStyleTag({ content: HIDE_BAR })
  await sync(page, 4000)

  const next = async hold => { await page.keyboard.press('ArrowRight'); await wait(page, hold) }

  await wait(page, 11)                     // 01 · the tier control
  await next(11)                           //      Conservative — three names left
  await next(10)                           //      Aggressive — empty, and says so
  await next(10)                           //      Balanced — the dimmed names stay visible
  await next(14)                           // 02 · all fifty-two as dots
  await next(13)                           //      the two axes
  await next(15)                           //      the corner the product exists for
  await next(18)                           // 03 · RHB Bank, the zero ring vs the live shape
  await next(6)                            //      the dated trail
  for (let i = 0; i < 14; i++) {           //      drift down it — a still list reads as a picture
    await page.mouse.move(960, 540)        //      of nothing happening, which is the opposite
    await page.mouse.wheel(0, 60)          //      of the claim being made over it
    await wait(page, 0.7)
  }
  await wait(page, 2)
  await next(16)                           //      what the verdict is standing on
  await ctx.close()
}

// ── take B · chapter 4, the Context tab: method, not one company ────────────────────────
async function takeB(browser) {
  const { ctx, page } = await open(browser, join(RAW, 'B'))
  await page.goto(`${APP}/`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(4000)
  await page.getByRole('button', { name: 'Context', exact: true }).click()
  await page.waitForTimeout(4000)

  const scrollTo = re => page.evaluate(r => {
    const el = [...document.querySelectorAll('h2,h3,div,section')]
      .find(e => new RegExp(r, 'i').test((e.textContent || '').slice(0, 80)))
    el?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    return !!el
  }, re)

  await scrollTo('^ESG momentum')
  await sync(page, 2000)

  await wait(page, 15)                     // momentum replayed at each quarter cutoff
  await scrollTo('^Has the verdict moved before')
  await wait(page, 11)                     // Sembcorp — signals years ahead of recognition
  await page.getByRole('button', { name: /Adaro/ }).click()
  await wait(page, 9)                      // and the case we got wrong, shipped on purpose
  await page.getByRole('button', { name: 'Board', exact: true }).click()
  await page.waitForTimeout(2200)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  await wait(page, 8)                      // back to the board, wide
  await ctx.close()
}

// ── take C · the whole analyst reel, driven through Solving for the 10% ─────────────────
/* One take, five chapters, because the track never leaves the app: unlike the 3-minute reel
   there is no second view to walk, so a single continuous recording keeps the cuts honest —
   every boundary below is a real moment in one session rather than a join between two.

   The holds are LONGER on chapter 04 than anywhere else, and deliberately so. It is the only
   chapter carrying numbers a viewer has to read rather than a picture they can take in: two
   stage panels, five per-cutoff bars and three caveat paragraphs. Giving it the same 20 seconds
   as the price strip would put the argument on screen too briefly to check, which is the exact
   thing the panel exists to refuse. */
async function takeAnalyst(browser) {
  const { ctx, page } = await open(browser, join(RAW, 'C'))
  await page.goto(`${APP}/?analyst=1`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1600)
  await page.addStyleTag({ content: HIDE_BAR })
  // Longer settle than take A: step 1 opens the evidence panel, which fetches before it paints.
  await sync(page, 5000)

  const next = async hold => { await page.keyboard.press('ArrowRight'); await wait(page, hold) }

  /* The holds ARE the narration budget. `docs/pitch/video/analyst/script.md` is written to
     150 words a minute against exactly these numbers, so changing one here without re-checking
     the word counts there produces a script that overruns its own footage — which is how the
     first cut of this reel came out at 280 wpm. */
  await wait(page, 30)                     // 01 · where the number comes from
  await next(21)                           // 02 · the zero ring against the live shape
  await next(21)                           //      all of them at once, on the two axes
  await next(22)                           // 03 · what the market already did about it
  await next(30)                           // 04 · stage one — the factor model, and it fails
  await next(30)                           //      stage two, with every qualifier beside it
  await next(12)                           // 05 · what would change the verdict
  await next(4)                            //      the trail itself
  for (let i = 0; i < 12; i++) {           //      drift down it: a still list of sources reads
    await page.mouse.move(960, 540)        //      as a picture of nothing happening, which is
    await page.mouse.wheel(0, 60)          //      the opposite of the claim being made over it
    await wait(page, 0.6)
  }
  await wait(page, 4)
  await next(30)                           // 06 · what better sources are worth
  await ctx.close()
}

// ── cut ─────────────────────────────────────────────────────────────────────────────────
/* Chapter lengths are the DELIVERABLE's contract — 42 + 42 + 52 + 44 = exactly 3:00 — and the
   narration in docs/pitch-demo-video-3min.md is written to them. They are offsets from each
   take's own sync frame, so a slower machine changes nothing about where a chapter starts. */
const CHAPTERS = [
  ['ch1', 'A', 0, 42],
  ['ch2', 'A', 42, 42],
  ['ch3', 'A', 84, 52],
  ['ch4', 'B', 0, 44],
]

/* The analyst reel: 30 + 42 + 22 + 60 + 26 + 30 = exactly 3:30, all offsets from take C's own
   sync frame. Chapter 04 is the longest on purpose — see the note on `takeAnalyst`. These must
   stay in step with the per-chapter durations in `docs/pitch/video/analyst/script.md`. */
const ANALYST_CHAPTERS = [
  ['ch1', 'C', 0, 30],
  ['ch2', 'C', 30, 42],
  ['ch3', 'C', 72, 22],
  ['ch4', 'C', 94, 60],
  ['ch5', 'C', 154, 26],
  ['ch6', 'C', 180, 30],
]

const browser = await chromium.launch()
rmSync(RAW, { recursive: true, force: true })
mkdirSync(RAW, { recursive: true })
mkdirSync(OUT, { recursive: true })

let CUTS, takes
if (ANALYST) {
  console.log('take C · the analyst reel, 6 chapters (3m30s of real time)…')
  await takeAnalyst(browser)
  await browser.close()
  CUTS = ANALYST_CHAPTERS
  takes = { C: only(join(RAW, 'C')) }
} else {
  console.log('take A · chapters 1-3 (about 2m20s of real time)…')
  await takeA(browser)
  console.log('take B · chapter 4 (about 55s)…')
  await takeB(browser)
  await browser.close()
  CUTS = CHAPTERS
  takes = { A: only(join(RAW, 'A')), B: only(join(RAW, 'B')) }
}
const zero = Object.fromEntries(Object.entries(takes).map(([k, f]) => [k, syncPoint(f)]))
console.log('sync frames:', zero)

for (const [name, take, start, dur] of CUTS) {
  sh('ffmpeg', ['-y', '-v', 'error', '-ss', String(zero[take] + start), '-i', takes[take],
    '-t', String(dur), '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
    '-pix_fmt', 'yuv420p', '-r', '30', '-g', '30', '-movflags', '+faststart',
    join(OUT, `${name}.mp4`)])
  console.log(`  ${name}.mp4  ${dur}s`)
}

writeFileSync(join(RAW, 'sync.json'), JSON.stringify({ zero, chapters: CUTS }, null, 1))
console.log(`\ndone — ${OUT}`)
