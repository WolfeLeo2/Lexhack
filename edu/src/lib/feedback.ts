// Small sounds (synthesised with Web Audio, no files) and haptics (Android vibrate) for actions the reader takes.
import { useSyncExternalStore } from 'react'

let on = localStorage.getItem('lexhack-sound') !== 'off'
const listeners = new Set<() => void>()
let ctx: AudioContext | null = null

export function useSound() {
  const enabled = useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => on,
  )
  const toggle = () => {
    on = !on
    localStorage.setItem('lexhack-sound', on ? 'on' : 'off')
    listeners.forEach((l) => l())
    if (on) play('tick')
  }
  return { enabled, toggle }
}

type Cue = 'tick' | 'stamp' | 'turn' | 'flag'

export function play(cue: Cue) {
  if (!on) return
  navigator.vibrate?.(cue === 'stamp' ? [18, 30, 12] : cue === 'flag' ? [10, 40, 10] : 8)
  ctx ??= new AudioContext()
  const t = ctx.currentTime
  const out = ctx.createGain()
  out.connect(ctx.destination)
  if (cue === 'tick' || cue === 'turn') {
    // a dry paper tick: a filtered noise burst
    const len = cue === 'turn' ? 0.09 : 0.025
    const buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * len), ctx.sampleRate)
    const d = buf.getChannelData(0)
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length) ** 2
    const src = ctx.createBufferSource()
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = cue === 'turn' ? 2600 : 4200
    bp.Q.value = 0.8
    src.buffer = buf
    src.connect(bp).connect(out)
    out.gain.value = cue === 'turn' ? 0.18 : 0.12
    src.start(t)
    return
  }
  // stamp: a soft low thud; flag: two short falling tones
  const osc = ctx.createOscillator()
  osc.connect(out)
  if (cue === 'stamp') {
    osc.type = 'sine'
    osc.frequency.setValueAtTime(140, t)
    osc.frequency.exponentialRampToValueAtTime(48, t + 0.16)
    out.gain.setValueAtTime(0.35, t)
    out.gain.exponentialRampToValueAtTime(0.001, t + 0.22)
    osc.start(t)
    osc.stop(t + 0.24)
  } else {
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(660, t)
    osc.frequency.setValueAtTime(494, t + 0.09)
    out.gain.setValueAtTime(0.0001, t)
    out.gain.exponentialRampToValueAtTime(0.12, t + 0.01)
    out.gain.exponentialRampToValueAtTime(0.001, t + 0.24)
    osc.start(t)
    osc.stop(t + 0.26)
  }
}
