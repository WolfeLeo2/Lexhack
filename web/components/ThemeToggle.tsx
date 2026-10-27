'use client'
import { Moon02Icon, Sun03Icon } from '@hugeicons/core-free-icons'
import { useSyncExternalStore } from 'react'
import { Glyph } from './Glyph'

type Theme = 'light' | 'dark'

/** Runs in <head> before first paint: a saved choice wins, otherwise the system setting. No flash of the wrong theme. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem('theme');document.documentElement.dataset.theme=t==='dark'||t==='light'?t:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}catch(e){}`

// The theme lives on <html data-theme>; subscribe to that attribute rather than copying it into React state.
function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb)
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => mo.disconnect()
}
const current = () => (document.documentElement.dataset.theme as Theme) ?? 'light'

/** Icon only in the header; `labelled` is the full-width row inside the mobile menu. */
export function ThemeToggle({ labelled = false }: { labelled?: boolean }) {
  const theme = useSyncExternalStore(subscribe, current, () => null)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  const icon = theme && (theme === 'dark' ? <Glyph key="moon" icon={Moon02Icon} className="theme-icon h-[1.15rem] w-[1.15rem]" /> : <Glyph key="sun" icon={Sun03Icon} className="theme-icon h-[1.15rem] w-[1.15rem]" />)
  return (
    <button
      type="button"
      onClick={() => {
        document.documentElement.dataset.theme = next
        try {
          localStorage.setItem('theme', next)
        } catch {}
      }}
      aria-label={labelled ? undefined : `Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={
        labelled
          ? 'flex min-h-11 w-full items-center gap-3 px-5 text-left text-ink-2 transition-colors hover:bg-panel hover:text-ink'
          : 'grid h-11 w-11 shrink-0 place-items-center rounded-md text-ink-2 transition-colors hover:bg-panel hover:text-ink'
      }
    >
      {labelled ? <span className="grid h-5 w-5 place-items-center">{icon}</span> : icon}
      {labelled && `Switch to ${next} theme`}
    </button>
  )
}
