'use client'
import { Cancel01Icon, Menu01Icon, Search01Icon } from '@hugeicons/core-free-icons'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Glyph } from './Glyph'
import { ThemeToggle } from './ThemeToggle'

/** Below md the header holds the logo, search and a hamburger; the links and the theme switch live in the panel. */
export function MobileMenu({ links }: { links: { href: string; label: string }[] }) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const path = usePathname()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      button.current?.focus()
    }
    const onDown = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  return (
    <div ref={wrap} className="ml-auto flex items-center md:hidden">
      <Link href="/search" aria-label="Search sections" className="grid h-11 w-11 place-items-center text-ink-2 hover:text-ink">
        <Glyph icon={Search01Icon} className="h-5 w-5" />
      </Link>
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls="mobile-menu"
        aria-label="Menu"
        onClick={() => setOpen((o) => !o)}
        className="grid h-11 w-11 place-items-center rounded-md hover:bg-panel"
      >
        <Glyph icon={open ? Cancel01Icon : Menu01Icon} className="h-6 w-6" />
      </button>
      {open && (
        <div id="mobile-menu" className="step-in absolute inset-x-0 top-full border-b border-rule bg-paper py-2 shadow-[0_18px_30px_-22px_rgb(var(--shadow-rgb)/0.5)]">
          <nav aria-label="Main">
            <ul>
              {links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    onClick={() => setOpen(false)}
                    aria-current={path === l.href || path.startsWith(`${l.href}/`) ? 'page' : undefined}
                    className="statute flex min-h-12 items-center px-5 text-xl aria-[current=page]:text-seal hover:bg-panel"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="mt-2 border-t border-rule pt-2">
            <ThemeToggle labelled />
          </div>
        </div>
      )}
    </div>
  )
}
