/**
 * record_competition_reel.mjs — stage 1 of the 2:30 competition reel: the FOOTAGE.
 *
 *   python -m scripts.demo_reset        # pre-warm the Compete answers (billable, once)
 *   python server.py                    # the app has to be up; this drives the real thing
 *   node scripts/record_competition_reel.mjs
 *       -> docs/pitch/video/reel/assets/ch01..ch10.mp4
 *   cd docs/pitch/video/reel && npx hyperframes render \
 *       --quality high --video-frame-format png --fps 30      # stage 2: slates + camera
 *
 * The narration this is cut to is `docs/pitch-competition-2min.md`. Chapter durations here and
 * scene windows there are the same numbers; if you change one, change the other, and re-run the
 * word-count check at the foot of that file.
 *
 * WHY THIS EXISTS ALONGSIDE `record_demo_reel.mjs`
 * ------------------------------------------------
 * The old reel is a 3:00 cut that lives almost entirely inside the app's own **Why it matters**
 * track: twelve arrow-key presses on one view. It still builds, and it is kept.
 *
 * This one cannot work that way. The 2:30 script spans THREE views — the board, the deep dive and
 * the evidence panel — and most of what it shows (the module picker, the two momentum directions,
 * the PPP triangle, the Forward View, the tamper demo) is not in any present track. So this
 * drives the app directly, by the same controls a person would click.
 *
 * RECORDED OUT OF ORDER, CUT INTO ORDER
 * --------------------------------------
 * The script alternates between views — board, deep dive, board, deep dive, board, evidence — and
 * following that literally would mean six navigations mid-take, each one a chance for the page to
 * settle differently. Chapters are cut at measured offsets and concatenated afterwards, so the
 * TAKE is grouped by view and the DELIVERABLE is still in script order. `SCENES` below is the
 * single source of both: `at` is where a scene starts in the take, `n` is where it sits in the
 * finished reel.
 *
 * FIVE THINGS ARE LOAD-BEARING. The first four cost a rebuild to learn on the previous reel; the
 * fifth cost one on this one.
 *
 * 1. THE PRESENT BAR IS HIDDEN WITH `opacity: 0`, NEVER `display: none`. `lib/anchor` reserves
 *    the bar's height as the CONSTANT `PRESENT_BAR_H` rather than measuring the DOM, so hiding it
 *    any other way leaves every highlight ring measuring against a band that is no longer there.
 *    Making it transparent changes nothing about the measurement, which is the point.
 *
 * 2. PAGE ZOOM IS NOT AN OPTION for legibility. `documentElement.style.zoom` does enlarge the UI,
 *    and it desynchronises `getBoundingClientRect` from what is painted, so anything positioned
 *    against a measurement lands near — but not on — its subject. Capture is native 1920x1080 and
 *    legibility is bought with the camera in the composition instead.
 *
 * 3. THE CUT POINTS COME FROM THE PICTURE, NOT FROM THIS SCRIPT'S CLOCK. Chromium's screencast
 *    starts before the page settles and keeps writing after the last action, so the wall-clock
 *    time of an action here is up to four seconds adrift from the frame it produced. The take
 *    opens on a solid MAGENTA SYNC FRAME — one full-frame colour nothing in the app can imitate —
 *    removed exactly at t=0. `ffmpeg select='gt(scene,0.5)'` finds that single transition and
 *    every offset below is measured from it.
 *
 * 4. RENDER STAGE 2 WITH `--video-frame-format png`. The default extracts source frames as JPEG,
 *    and JPEG ringing on a dark UI full of 1px rules and 11px monospace is visible at slide size.
 *
 * 5. THE BOARD IS TALLER THAN THE VIEWPORT, so every scene scrolls its subject into frame FIRST
 *    and then holds. A scene that starts mid-scroll reads as a fumble, and `scrollIntoView` with
 *    `behavior: 'smooth'` is still animating for several hundred milliseconds after it returns —
 *    hence the wait inside `show()` rather than an immediate hold.
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, rmSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = await import(join(ROOT, 'web/node_modules/playwright/index.mjs'))

const APP = process.env.ESG_APP_URL || 'http://localhost:8000'
const OUT = join(ROOT, 'docs/pitch/video/reel/assets')
const RAW = join(ROOT, 'docs/pitch/video/reel/raw-competition')

/** The company the whole reel follows. Its figures are quoted in the narration. */
const SUBJECT = 'KLSE:RHBBANK'

/*
 * Every UI flag spelled out, including the ones that default the other way. Anything omitted
 * falls back to the app's DEFAULTS, which are written for a first-time visitor — `tourDone` is
 * the one that bites: leaving it out arms the first-run tutorial, so a coach-mark overlay can
 * appear mid-take on the exact screen this script exists to make identical.
 *
 * `focus` is pinned to the subject so scenes 6-8 have a company on the board without a click,
 * and `level: 3` because every panel the script names is level-3 furniture.
 */
const SETTINGS = {
  // `universe: 'cgsi'` and it never changes: the entire reel is CGSI's verified 52, which is the
  // only selection the basket-performance claim describes. See the note on S3.
  demo: false, dark: true, simplified: false, level: 3, tab: 'board',
  setupDone: true, tourDone: true, tourDeck: '', extras: [], focus: SUBJECT,
  profile: { mandate: 'risk', goal: 'screen', holding: '2_5y', focus: 'broad',
             label: 'protect the downside across ASEAN' },
  filters: { country: 'All', sector: 'All' }, leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', horizon: 'long', pipelineOnly: false,
  greenFocus: false, ppp: 'balanced', universe: 'cgsi',
}

const SYNC = `<div id="__sync" style="position:fixed;inset:0;z-index:2147483647;background:#ff00c8"></div>`
/* The present bar is not used by this take, but a stray `?present=1` in a re-run would bring it
   back — and rule 1 above applies whenever it exists. Cheap to keep. */
const HIDE_BAR = `.present-bar{opacity:0!important;pointer-events:none!important}`

const sh = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`${cmd} failed: ${r.stderr?.slice(0, 800)}`)
  return r.stdout + r.stderr
}

/** The one full-frame transition in the take: magenta -> the app. That frame is t=0. */
const syncPoint = file => {
  const out = sh('ffmpeg', ['-v', 'error', '-i', file, '-vf',
    "select='gt(scene,0.5)',metadata=print:file=-", '-an', '-f', 'null', '-'])
  const hit = out.match(/pts_time:([0-9.]+)/)
  if (!hit) throw new Error(`no sync frame found in ${file} — was the marker painted?`)
  return parseFloat(hit[1])
}

const only = dir => join(dir, readdirSync(dir).find(f => f.endsWith('.webm')))
const wait = (page, s) => page.waitForTimeout(s * 1000)

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

/** Bring a selector into frame and let the smooth scroll finish before anything is held on. */
async function show(page, selector, block = 'center') {
  await page.evaluate(([sel, b]) => {
    document.querySelector(sel)?.scrollIntoView({ block: b, behavior: 'smooth' })
  }, [selector, block])
  await page.waitForTimeout(900)
}

/** Click a button by its exact visible label inside a labelled segmented control. */
const seg = (page, label, text) =>
  page.locator(`.seg[aria-label="${label}"] button`, { hasText: new RegExp(`^${text}$`) }).first()

/* ── the take ─────────────────────────────────────────────────────────────────────────────
 *
 * Grouped by VIEW, not by script order — see the header. Every hold is the scene's own window
 * from `docs/pitch-competition-2min.md`, plus a beat at the head of each for the scroll to land.
 */
async function take(browser) {
  const { ctx, page } = await open(browser, RAW)
  await page.goto(APP, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  await page.addStyleTag({ content: HIDE_BAR })
  await page.waitForSelector('.matrix-dot', { timeout: 30000 })
  await sync(page, 3500)

  // ── BOARD ──────────────────────────────────────────────────────────────────────────────
  // S1 · the matrix, four quadrants, hollow dots visible (13s)
  await show(page, '[data-tour="matrix"]', 'start')
  await page.mouse.move(1150, 480)
  await wait(page, 4)
  await page.mouse.move(1180, 700, { steps: 40 })   // top-right -> bottom-right, slowly
  await wait(page, 5)
  await page.mouse.move(760, 620, { steps: 30 })
  await wait(page, 4)

  // S2 · mandate re-segmentation, Conservative -> Balanced (10s)
  await show(page, '[data-tour="tiers"]', 'center')
  await seg(page, 'Risk appetite', 'Conservative').click()
  await wait(page, 5)
  await seg(page, 'Risk appetite', 'Balanced').click()
  await wait(page, 5)

  // S3 · she builds her own board — the module chips and the level (9s)
  //
  // THE UNIVERSE CONTROL IS DELIBERATELY NOT TOUCHED. The whole reel is the CGSI 52, and the
  // basket-performance claim the pitch rests on describes that selection and nothing else.
  // Flipping to the 185-name index universe mid-reel — even for three seconds, even flipping
  // back — puts a board on screen that the narration is not describing, and every figure spoken
  // over it (fifty-two companies, ten names, plus zero point seven eight) belongs to the other
  // one. Customisation reads perfectly well as layout alone.
  // The picker is demonstrated at PREFERENCES, not at Everything. At level 3 almost every module
  // is already native, so exactly one chip is offerable and the row has nothing to show; at
  // level 1 the picker is the whole point — six or seven panels to add one at a time. Dropping
  // down first is also the more honest demo: it is the reader choosing what to add back, rather
  // than removing something the level had already given them.
  await seg(page, 'Risk appetite', 'All').click()
  await seg(page, 'Detail level', 'Preferences').click()
  await page.waitForTimeout(1200)
  await show(page, '[data-tour="add-modules"]', 'center')
  await wait(page, 2)
  const chips = page.locator('.step-up-chip')
  const n = Math.min(2, await chips.count())
  for (let i = 0; i < n; i++) {
    await chips.nth(i).click()
    await wait(page, 2)
  }
  await seg(page, 'Detail level', 'Everything').click()
  await wait(page, 2.5)

  // S5 · the call list — the origination pipeline, M = 10 (8s)
  await show(page, '[data-tour="nmk"]', 'center')
  await page.locator('[data-tour="pipeline"]').click()
  await wait(page, 5)
  await page.locator('[data-tour="pipeline"]').click()   // back off, so S7 opens on a full board
  await wait(page, 3)

  // S7 · two directions, then the PPP triangle (18s)
  await show(page, '.dual', 'center')
  await wait(page, 7)
  await show(page, '.tri', 'center')
  await page.mouse.move(880, 560)
  await wait(page, 11)

  // S8 · the Forward View row (20s)
  await show(page, '.hub-fwd', 'center')
  await wait(page, 8)
  await page.mouse.move(300, 700)                        // the red NO MEASURED SKILL badge
  await wait(page, 6)
  await page.mouse.move(1300, 700, { steps: 30 })        // the green MEASURED badge
  await wait(page, 6)

  // ── DEEP DIVE ──────────────────────────────────────────────────────────────────────────
  // Pre-warmed by `scripts/demo_reset`, so this opens on a built entry rather than a spinner.
  await show(page, '.hub-cta', 'center')
  await page.locator('.hub-cta .btn', { hasText: /Shape the question first/ }).first().click()
  await page.waitForSelector('[data-tour="interrogate"], .lseg', { timeout: 30000 }).catch(() => {})
  await page.waitForTimeout(2500)

  // S4 · adaptive interrogation, four ESG-native axes (17s)
  await show(page, '[data-tour="interrogate"]', 'start')
  await wait(page, 6)
  const opener = page.locator('.iq-opener, .iq-suggest, .interrogation button').first()
  if (await opener.count()) { await opener.click(); await page.waitForTimeout(2500) }
  await wait(page, 9)

  // S6 · the live LSEG twelve-theme wheel (16s)
  await show(page, '.lseg', 'center')
  await wait(page, 9)
  await show(page, '.case-panel, [data-tour="verdict"]', 'center')
  await wait(page, 7)

  // ── EVIDENCE ───────────────────────────────────────────────────────────────────────────
  // BACK TO THE BOARD VIA THE HEADER, never `goBack()`. The app's view is React state, not a
  // route — `setView`, not the URL — so browser history has nothing to return to and the first
  // build sat on the deep dive until the next locator timed out.
  await page.locator('.cc-hdr button', { hasText: /^Dashboard$/ }).first().click()
  await page.waitForTimeout(1500)
  await page.evaluate(() => window.scrollTo({ top: 0 }))
  await show(page, '[data-tour="matrix"]', 'start')
  await wait(page, 1)

  // INTO THE EVIDENCE TRAIL by the hidden-winner shortcut, which is one click and does both
  // halves — `setFocus` then `openEvidence`. The two-stage dot click is the documented path for
  // a person, and it is the wrong path for a machine: it needs the dot to already carry
  // `is-focus`, which depends on state surviving a view change, and the first build timed out
  // waiting for exactly that. The shortcut has no such precondition.
  const pick = page.locator('.hw-pick', { hasText: /RHB/ }).first()
  if (await pick.count()) {
    await pick.click()
  } else {
    const dot = page.locator('.matrix-dot.is-focus, .matrix-dot.q-hidden').first()
    await dot.click({ force: true })
    await page.waitForTimeout(700)
    await dot.click({ force: true })
  }
  await page.waitForSelector('[data-tour="trail"]', { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(1500)

  // S9 · three clicks to source (16s)
  await show(page, '[data-tour="trail"]', 'start')
  await wait(page, 5)
  for (let i = 0; i < 8; i++) {          // drift down the trail — a still list reads as a picture
    await page.mouse.move(960, 620)      // of nothing happening, which is the opposite of the
    await page.mouse.wheel(0, 70)        // claim being made over it
    await wait(page, 0.8)
  }
  await wait(page, 4)

  // S10 · verification and the tamper demo (16s)
  await show(page, '[data-tour="verify-block"]', 'center')
  await page.locator('button', { hasText: /Verify this evidence/ }).first().click()
  await page.waitForTimeout(3000)
  await wait(page, 3)
  await page.locator('button', { hasText: /Tamper demo/ }).first().click()
  await page.waitForTimeout(3000)
  await wait(page, 3)
  await page.locator('button', { hasText: /Verify this evidence/ }).first().click()
  await page.waitForTimeout(2500)
  await wait(page, 2)

  await ctx.close()
}

/* ── the cut ──────────────────────────────────────────────────────────────────────────────
 *
 * `n` is the scene's place in the FINISHED reel; `at` is where it starts in the take. They differ
 * because the take is grouped by view — see the header. `dur` is the scene's window in
 * `docs/pitch-competition-2min.md` and the two must stay equal.
 *
 * The offsets below are the sum of the holds above and are a STARTING POINT, not a guarantee:
 * rule 3 says the picture decides. Run once, watch `raw-competition/`, and nudge `at` until each
 * chapter opens on its subject. `sync.json` records what was used.
 */
const SCENES = [
  { n: 1, at: 0, dur: 13, name: 'the board and the core thesis' },
  { n: 2, at: 14, dur: 10, name: 'mandate re-segmentation' },
  { n: 3, at: 25, dur: 9, name: 'she builds her own board' },
  { n: 5, at: 35, dur: 8, name: 'the call list' },
  { n: 7, at: 44, dur: 18, name: 'two directions, and the triangle' },
  { n: 8, at: 63, dur: 20, name: 'the forecast that reports its failure' },
  { n: 4, at: 88, dur: 17, name: 'adaptive interrogation' },
  { n: 6, at: 106, dur: 16, name: 'the live LSEG wheel' },
  { n: 9, at: 128, dur: 16, name: 'three clicks to source' },
  { n: 10, at: 146, dur: 16, name: 'verification and the tamper demo' },
]

const browser = await chromium.launch()
rmSync(RAW, { recursive: true, force: true })
mkdirSync(RAW, { recursive: true })
mkdirSync(OUT, { recursive: true })
console.log('one take, about 3m of real time…')
await take(browser)
await browser.close()

const src = only(RAW)
const zero = syncPoint(src)
console.log('sync frame at', zero.toFixed(2), 's')

for (const s of [...SCENES].sort((a, b) => a.n - b.n)) {
  const out = join(OUT, `ch${String(s.n).padStart(2, '0')}.mp4`)
  sh('ffmpeg', ['-y', '-v', 'error', '-ss', String(zero + s.at), '-i', src,
    '-t', String(s.dur), '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
    '-pix_fmt', 'yuv420p', '-r', '30', '-g', '30', '-movflags', '+faststart', out])
  console.log(`  ch${String(s.n).padStart(2, '0')}.mp4  ${String(s.dur).padStart(2)}s  ${s.name}`)
}

writeFileSync(join(RAW, 'sync.json'), JSON.stringify({ zero, scenes: SCENES }, null, 1))
const total = SCENES.reduce((a, s) => a + s.dur, 0)
console.log(`\ndone — ${OUT}`)
console.log(`${SCENES.length} chapters, ${total}s of picture (+0:07 silent end card = ${total + 7}s)`)
console.log('watch raw-competition/ and nudge SCENES[].at until each chapter opens on its subject.')
