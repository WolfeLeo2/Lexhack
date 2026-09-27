import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import type { CourtEvent } from '../lib/types.ts'

export const EVENT_LABEL: Record<string, string> = {
  declared_unconstitutional: 'Declared unconstitutional',
  read_down: 'Read down',
  severed: 'Severed',
  upheld: 'Upheld',
  interpreted: 'Interpreted',
  reversed_on_appeal: 'Reversed on appeal',
  repealed_by_statute: 'Repealed by Parliament',
  amended_by_statute: 'Amended by Parliament',
}

export const year = (d: string | null) => (d ?? '').slice(0, 4)

export const shortCase = (e: Pick<CourtEvent, 'title'>) =>
  (e.title ?? '').replace(/\s*[([;].*$/, '')

export function fmtDate(d: string | null) {
  if (!d) return ''
  return new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** A part of the page, numbered like the sections of an Act. */
export function Part({
  id,
  n,
  title,
  lede,
  children,
}: {
  id: string
  n: number
  title: string
  lede?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} className="border-t border-rule py-16 sm:py-20" aria-labelledby={`${id}-h`}>
      <div className="relative max-w-[68ch]">
        <span className="statute absolute -left-14 top-1 hidden w-10 text-right text-3xl text-ink-2/60 lg:block" aria-hidden>
          {n}.
        </span>
        <h2 id={`${id}-h`} className="statute text-[2.1rem] leading-tight font-medium tracking-[-0.01em] sm:text-[2.6rem]">
          <span className="text-ink-2/60 lg:hidden">{n}. </span>
          {title}
        </h2>
        {lede && <div className="prose-body mt-5 text-lg text-ink-2">{lede}</div>}
      </div>
      <div className="mt-10">{children}</div>
    </section>
  )
}

/** The court's exact words, with the limiting clause marked where it appears inside the quote. */
export function CourtWords({ quote, mark, className = '' }: { quote: string; mark?: string | null; className?: string }) {
  const i = mark ? quote.toLowerCase().indexOf(mark.toLowerCase()) : -1
  return (
    <blockquote className={`court ${className}`}>
      “
      {i < 0 || !mark ? (
        <span className="hl">{quote}</span>
      ) : (
        <>
          {quote.slice(0, i)}
          <span className="hl">{quote.slice(i, i + mark.length)}</span>
          {quote.slice(i + mark.length)}
        </>
      )}
      ”
    </blockquote>
  )
}

/** Status is always words, never a colour-coded yes/no. The stamp's ink only says whether a court has acted. */
export function StatusStamp({ status, animate = true }: { status: string; animate?: boolean }) {
  const reduce = useReducedMotion()
  const courtActed = !status.includes('no recorded')
  return (
    <motion.div
      key={status}
      initial={animate && !reduce ? { scale: 1.35, opacity: 0, rotate: -5 } : false}
      animate={{ scale: 1, opacity: 1, rotate: -1.5 }}
      transition={{ type: 'spring', stiffness: 520, damping: 22 }}
      className={`inline-block rounded-[3px] border-2 px-3 py-1.5 font-medium ${
        courtActed ? 'border-seal text-seal' : 'border-ink-2/50 text-ink-2'
      }`}
      role="status"
    >
      <span className="block text-[0.7rem] leading-none opacity-80">Status today</span>
      <span className="statute text-lg leading-tight">{status[0].toUpperCase() + status.slice(1)}</span>
    </motion.div>
  )
}

export function StateTag({ state }: { state: CourtEvent['state'] }) {
  if (state === 'in effect') return <span className="text-sm text-gazette">Still counts</span>
  return <span className="text-sm text-ink-2 line-through decoration-seal/60">{state[0].toUpperCase() + state.slice(1)}</span>
}

export function Button({
  children,
  onClick,
  variant = 'solid',
  disabled,
  className = '',
  ...rest
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'solid' | 'ghost'
  disabled?: boolean
  className?: string
  'aria-pressed'?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-[0.95rem] font-medium transition-colors disabled:opacity-40 ${
        variant === 'solid'
          ? 'bg-ink text-paper hover:bg-gazette'
          : 'border border-rule bg-paper text-ink hover:border-ink-2 aria-pressed:border-ink aria-pressed:bg-ink aria-pressed:text-paper'
      } ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
