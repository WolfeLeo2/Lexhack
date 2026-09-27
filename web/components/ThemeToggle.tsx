'use client'
import { Moon, Sun } from 'lucide-react'
import { useSyncExternalStore } from 'react'

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

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, current, () => null)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={() => {
        document.documentElement.dataset.theme = next
        try {
          localStorage.setItem('theme', next)
        } catch {}
      }}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 transition-colors hover:bg-panel hover:text-ink"
    >
      {theme &&
        (theme === 'dark' ? (
          <Moon key="moon" className="theme-icon h-[1.15rem] w-[1.15rem]" aria-hidden />
        ) : (
          <Sun key="sun" className="theme-icon h-[1.15rem] w-[1.15rem]" aria-hidden />
        ))}
    </button>
  )
}
