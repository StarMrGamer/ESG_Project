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
/** How long the marker is held. `syncPoint` looks for an interval exactly this long, so the two
 *  are one constant rather than two numbers that have to be remembered together. */
const SYNC_HOLD_MS = 3500
/* The present bar is not used by this take, but a stray `?present=1` in a re-run would bring it
   back — and rule 1 above applies whenever it exists. Cheap to keep. */
const HIDE_BAR = `.present-bar{opacity:0!important;pointer-events:none!important}`

const sh = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`${cmd} failed: ${r.stderr?.slice(0, 800)}`)
  return r.stdout + r.stderr
}

/**
 * Where the magenta marker ENDS. That frame is t=0.
 *
 * The marker produces TWO full-frame transitions, not one: the app -> magenta when it is painted,
 * and magenta -> the app when it is removed. Only the second is t=0. The first build took the
 * first match and every chapter opened on a full screen of magenta — the cut was 3.5 seconds
 * early, uniformly, which looks like a broken encoder rather than a wrong offset.
 *
 * So the marker is found as an INTERVAL rather than an edge: the pair of transitions separated by
 * the hold it was held for. That is what the marker actually is, it does not care how many other
 * transitions the take contains, and it fails loudly rather than guessing if the pair is absent.
 */
const syncPoint = (file, holdMs) => {
  const out = sh('ffmpeg', ['-v', 'error', '-i', file, '-vf',
    "select='gt(scene,0.3)',metadata=print:file=-", '-an', '-f', 'null', '-'])
  const times = [...out.matchAll(/pts_time:([0-9.]+)/g)].map(m => parseFloat(m[1]))
  if (times.length < 2) {
    throw new Error(`only ${times.length} transition(s) in ${file} — was the marker painted?`)
  }
  const hold = holdMs / 1000
  // Half a second of slack: the screencast quantises to frames and the paint is not instant.
  const pair = times.slice(1).findIndex((t, i) => Math.abs(t - times[i] - hold) < 0.6)
  if (pair === -1) {
    throw new Error(`no ${hold}s magenta interval in ${file} — found transitions at `
      + `${times.join(', ')}. Did the hold change without this being told?`)
  }
  return times[pair + 1]
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

/**
 * WHERE EACH SCENE ACTUALLY STARTS, measured rather than hand-summed.
 *
 * The first build declared `SCENES[].at` as the running sum of the holds above it, and three
 * chapters opened on the wrong panel: every `waitForSelector`, every network round trip and every
 * scroll settle adds time the arithmetic does not know about, and the error accumulates down the
 * take. Chapter 4 was perfect and chapters 3 and 5 were seconds out — which is the signature of
 * drift, not of one bad number.
 *
 * So the take timestamps itself. `mark()` records the seconds elapsed since the marker was
 * removed — the same instant `syncPoint` finds in the picture — so the two clocks share an
 * origin. Rule 3 above still holds for the START of the screencast, which is exactly what the
 * marker corrects for; once t=0 is known from the picture, elapsed time measured in the page is
 * accurate to a frame or two.
 */
const MARKS = []
let T0 = 0
const mark = (n, name) => { MARKS.push({ n, name, at: +((Date.now() - T0) / 1000).toFixed(2) }) }

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
  await sync(page, SYNC_HOLD_MS)
  T0 = Date.now()

  // ── BOARD ──────────────────────────────────────────────────────────────────────────────
  // S1 · the matrix, four quadrants, hollow dots visible (13s)
  mark(1, 'the board and the core thesis')
  await show(page, '[data-tour="matrix"]', 'start')
  await page.mouse.move(1150, 480)
  await wait(page, 4)
  await page.mouse.move(1180, 700, { steps: 40 })   // top-right -> bottom-right, slowly
  await wait(page, 5)
  await page.mouse.move(760, 620, { steps: 30 })
  await wait(page, 4)

  // S2 · mandate re-segmentation, Conservative -> Balanced (10s)
  await show(page, '[data-tour="tiers"]', 'center')
  mark(2, 'mandate re-segmentation')
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
  mark(3, 'she builds her own board')
  await wait(page, 2)
  // PINNED BY NAME, never "the first two". The picker offers `Side rails` among them, and
  // clicking it opens both rails — which narrows the centre column for the REST of the take, so
  // scenes 7 and 8 played out with the dual card and the triangle squeezed into a third of the
  // width they are designed for. A layout change here is not local to this scene.
  //
  // These two are panels, not layout: they appear in place and leave the column alone.
  for (const name of ['Disagreement matrix', 'Why the verdict']) {
    const chip = page.locator('.step-up-chip', { hasText: name }).first()
    if (await chip.count()) {
      await chip.click()
      await wait(page, 2)
    }
  }
  await seg(page, 'Detail level', 'Everything').click()
  await wait(page, 2.5)

  // AND CLOSE THE RAILS THE LEVEL BUTTON JUST OPENED. The header's level control is
  // `setSettings({ level, leftOpen: l.n > 1, rightOpen: l.n > 1 })` — by design, since Everything
  // means everything. But it narrows the centre column for the REST of the take, and scenes 7
  // and 8 are about panels that need the width: the triangle and the Forward View played out
  // squeezed into a third of what they are drawn for.
  //
  // The toggles live inside the ⚙ menu, so it is opened and closed again. That happens in the
  // gap between two chapters, never inside one.
  await page.locator('.cc-menu > summary').first().click()
  await page.waitForTimeout(500)
  for (const label of [/Filters/, /Assistant/]) {
    const b = page.locator('.cc-menu-body .btn', { hasText: label }).first()
    if (await b.count()) { await b.click(); await page.waitForTimeout(400) }
  }
  await page.keyboard.press('Escape')
  await page.waitForTimeout(800)

  // S5 · the call list — the origination pipeline, M = 10 (8s)
  await show(page, '[data-tour="nmk"]', 'center')
  mark(5, 'the call list')
  await page.locator('[data-tour="pipeline"]').click()
  await wait(page, 5)
  await page.locator('[data-tour="pipeline"]').click()   // back off, so S7 opens on a full board
  await wait(page, 3)

  // S7 · two directions, then the PPP triangle (18s)
  await show(page, '.dual', 'center')
  mark(7, 'two directions, and the triangle')
  await wait(page, 7)
  await show(page, '.tri', 'center')
  await page.mouse.move(880, 560)
  await wait(page, 11)

  // S8 · the Forward View row (20s)
  await show(page, '.hub-fwd', 'center')
  mark(8, 'the forecast that reports its failure')
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
  mark(4, 'adaptive interrogation')
  await wait(page, 6)
  const opener = page.locator('.iq-opener, .iq-suggest, .interrogation button').first()
  if (await opener.count()) { await opener.click(); await page.waitForTimeout(2500) }
  await wait(page, 9)

  // S6 · the live LSEG twelve-theme wheel (16s)
  //
  // `.lseg-wheel`, not `.lseg`. The first cut used the latter, which matches nothing — and
  // `show()` swallows a miss by design (`?.scrollIntoView`), so the take silently held on
  // whatever was already on screen and the chapter shipped without the wheel in it. A selector
  // that does nothing looks exactly like a selector that worked.
  await page.waitForSelector('.lseg-wheel', { timeout: 20000 }).catch(() => {})
  await show(page, '.lseg-wheel', 'center')
  mark(6, 'the live LSEG wheel')
  await wait(page, 9)
  await show(page, '.case-panel, [data-tour="verdict"]', 'center')
  await wait(page, 7)

  // ── EVIDENCE ───────────────────────────────────────────────────────────────────────────
  // BACK TO THE BOARD VIA THE HEADER, never `goBack()`. The app's view is React state, not a
  // route — `setView`, not the URL — so browser history has nothing to return to, and the first
  // build sat on the deep dive until the next locator timed out.
  //
  // Located by ROLE, not by container class. The second build guessed `.cc-hdr` and timed out;
  // the class is `cc-header`, and guessing a class again is the same mistake with a different
  // string. The app title is the documented fallback — `.cc-hdr-wrap` carries `onClick=
  // {goDashboard}` — so if the button is ever moved behind a menu this still lands on the board.
  const home = page.getByRole('button', { name: 'Dashboard', exact: true }).first()
  if (await home.count()) await home.click()
  else await page.locator('.cc-hdr-wrap').first().click()
  await page.waitForSelector('[data-tour="matrix"]', { timeout: 30000 })
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
  mark(9, 'three clicks to source')
  await wait(page, 5)
  for (let i = 0; i < 8; i++) {          // drift down the trail — a still list reads as a picture
    await page.mouse.move(960, 620)      // of nothing happening, which is the opposite of the
    await page.mouse.wheel(0, 70)        // claim being made over it
    await wait(page, 0.8)
  }
  await wait(page, 4)

  // S10 · verification and the tamper demo (16s)
  await show(page, '[data-tour="verify-block"]', 'center')
  mark(10, 'verification and the tamper demo')
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
 * Durations are the scene windows from the script. The OFFSETS are measured by `mark()` during
 * the take, never declared here — see the note above `mark`. `sync.json` records both.
 */
/** Scene DURATIONS only. `at` is measured by `mark()` during the take — see the note there. */
const DUR = { 1: 13, 2: 10, 3: 9, 4: 17, 5: 8, 6: 16, 7: 18, 8: 20, 9: 16, 10: 16 }

const browser = await chromium.launch()
rmSync(RAW, { recursive: true, force: true })
mkdirSync(RAW, { recursive: true })
mkdirSync(OUT, { recursive: true })
console.log('one take, about 3m of real time…')
await take(browser)
await browser.close()

const src = only(RAW)
const zero = syncPoint(src, SYNC_HOLD_MS)
console.log('sync frame at', zero.toFixed(2), 's')

const SCENES = MARKS.map(m => ({ ...m, dur: DUR[m.n] })).sort((a, b) => a.n - b.n)
const missing = Object.keys(DUR).map(Number).filter(n => !SCENES.some(s => s.n === n))
if (missing.length) throw new Error(`scene(s) ${missing.join(', ')} never ran — no mark recorded`)

for (const s of SCENES) {
  const out = join(OUT, `ch${String(s.n).padStart(2, '0')}.mp4`)
  sh('ffmpeg', ['-y', '-v', 'error', '-ss', String(zero + s.at), '-i', src,
    '-t', String(s.dur), '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
    '-pix_fmt', 'yuv420p', '-r', '30', '-g', '30', '-movflags', '+faststart', out])
  console.log(`  ch${String(s.n).padStart(2, '0')}.mp4  ${String(s.dur).padStart(2)}s  `
    + `@${String(s.at).padStart(6)}s  ${s.name}`)
}

writeFileSync(join(RAW, 'sync.json'), JSON.stringify({ zero, scenes: SCENES }, null, 1))
const total = SCENES.reduce((a, s) => a + s.dur, 0)
console.log(`\ndone — ${OUT}`)
console.log(`${SCENES.length} chapters, ${total}s of picture (+0:07 silent end card = ${total + 7}s)`)
console.log('offsets are MEASURED, not summed — see mark(). sync.json records what was used.')
