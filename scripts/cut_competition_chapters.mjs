/**
 * cut_competition_chapters.mjs — stage 1b: cut the take to the NARRATION, not to an estimate.
 *
 *   node scripts/record_competition_reel.mjs        # the take + sync.json
 *   node scripts/heygen_narration.mjs               # the wavs (or generate them by hand)
 *   node scripts/cut_competition_chapters.mjs       # -> assets/ch01..ch10.mp4, muxed
 *
 * WHY THIS IS A SEPARATE STEP
 * ---------------------------
 * The scene windows in `docs/pitch-competition-2min.md` are a PLANNING figure: words divided by
 * 125 per minute. They are close, and they are not the delivery. Measured against the real
 * narration, three chapters were shorter than the line they had to carry — by 0.4 to 0.6 seconds,
 * which is enough to clip the last word off a sentence.
 *
 * So a chapter's duration is derived from three measured things rather than declared:
 *
 *   1. the NARRATION for that scene, which is the floor — a clip shorter than its line truncates
 *      speech, and no amount of pacing fixes that in the edit;
 *   2. a BEAT after the line ends, so the picture does not cut on the closing consonant;
 *   3. the ROOM in the take before the next scene starts, which is the ceiling. Past it the
 *      chapter shows the next scene's scroll — two chapters were already doing this, bleeding
 *      1.5s and 1.1s into their neighbours' setup.
 *
 * `duration = clamp(audio + BEAT, audio, room)`. If room is ever smaller than the audio the run
 * FAILS rather than shipping a truncated line: that means the take did not hold long enough on
 * that scene, and the fix is in the take, not here.
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readdirSync } from 'node:fs'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const RAW = join(ROOT, 'docs/pitch/video/reel/raw-competition')
const OUT = join(ROOT, 'docs/pitch/video/reel/assets')
const VO = join(ROOT, 'docs/pitch/video/tts-competition')

/** A held beat after the last word, so the cut does not land on a closing consonant. */
const BEAT = 0.9

const sh = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`${cmd} failed: ${r.stderr?.slice(0, 600)}`)
  return r.stdout + r.stderr
}
const seconds = file => parseFloat(sh('ffprobe',
  ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]).trim())

const { zero, scenes } = JSON.parse(readFileSync(join(RAW, 'sync.json'), 'utf8'))
const src = join(RAW, readdirSync(RAW).find(f => f.endsWith('.webm')))
const takeEnd = seconds(src) - zero

// Room is measured against the NEXT scene in TAKE order, which is not script order.
const byTake = [...scenes].sort((a, b) => a.at - b.at)
const room = new Map(byTake.map((s, i) =>
  [s.n, (i + 1 < byTake.length ? byTake[i + 1].at : takeEnd) - s.at]))

const plan = []
for (const s of [...scenes].sort((a, b) => a.n - b.n)) {
  const wav = join(VO, `s${String(s.n).padStart(2, '0')}.wav`)
  const audio = existsSync(wav) ? seconds(wav) : 0
  const have = room.get(s.n)
  if (audio > have) {
    throw new Error(`scene ${s.n}: narration is ${audio.toFixed(2)}s but the take only holds `
      + `${have.toFixed(2)}s before the next scene starts. Lengthen the hold in `
      + `record_competition_reel.mjs and re-record — do not shorten the line to fit a take.`)
  }
  const dur = Math.min(have, Math.max(audio + BEAT, audio))
  plan.push({ ...s, audio, room: have, dur: +dur.toFixed(2), wav: existsSync(wav) ? wav : null })
}

console.log('  ch   start     dur   narration   room')
for (const p of plan) {
  const out = join(OUT, `ch${String(p.n).padStart(2, '0')}.mp4`)
  const args = ['-y', '-v', 'error', '-ss', String(zero + p.at), '-i', src]
  if (p.wav) args.push('-i', p.wav)
  args.push('-t', String(p.dur),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
    '-r', '30', '-g', '30', '-movflags', '+faststart')
  // The narration is padded to the clip rather than the clip trimmed to it: apad + -shortest
  // ends the file on the picture, so a chapter is always exactly `dur` however the beat lands.
  if (p.wav) args.push('-c:a', 'aac', '-b:a', '192k', '-af', 'apad', '-shortest')
  else args.push('-an')
  args.push(out)
  sh('ffmpeg', args)
  console.log(`  ${String(p.n).padStart(2, '0')}  ${String(p.at).padStart(6)}s  `
    + `${p.dur.toFixed(1).padStart(5)}s  ${p.audio.toFixed(1).padStart(6)}s  `
    + `${p.room.toFixed(1).padStart(6)}s${p.wav ? '' : '   (silent — no wav)'}`)
}

writeFileSync(join(RAW, 'cut.json'), JSON.stringify({ beat: BEAT, plan }, null, 1))
const total = plan.reduce((a, p) => a + p.dur, 0)
const spoken = plan.reduce((a, p) => a + p.audio, 0)
console.log(`\n  ${plan.length} chapters · ${total.toFixed(1)}s of picture · `
  + `${spoken.toFixed(1)}s spoken · +0:07 end card = ${(total + 7).toFixed(0)}s`)
