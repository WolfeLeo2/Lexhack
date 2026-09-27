import { Search } from 'lucide-react'

/** A plain GET form: works before JavaScript loads, and the query lives in the URL so results can be shared. */
export function SearchBox({ defaultValue = '', size = 'lg' }: { defaultValue?: string; size?: 'sm' | 'lg' }) {
  const lg = size === 'lg'
  return (
    <form action="/search" role="search" className="relative">
      <label htmlFor={`q-${size}`} className="sr-only">
        Search sections
      </label>
      <Search
        className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-ink-2 ${lg ? 'left-4 h-5 w-5' : 'left-3 h-4 w-4'}`}
        aria-hidden
      />
      <input
        id={`q-${size}`}
        name="q"
        type="search"
        required
        minLength={2}
        defaultValue={defaultValue}
        placeholder={lg ? 'Search a section, e.g. “libel” or “defilement”' : 'Search sections'}
        className={`w-full rounded-md border border-rule bg-paper/80 text-ink placeholder:text-ink-2/70 focus:border-ink focus:outline-none ${
          lg ? 'py-3.5 pr-4 pl-12 text-lg shadow-[0_1px_0_var(--color-rule)]' : 'py-1.5 pr-3 pl-9 text-[0.95rem]'
        }`}
      />
    </form>
  )
}
