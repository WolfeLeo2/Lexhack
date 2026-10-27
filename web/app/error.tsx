'use client'
import Link from 'next/link'
import { useEffect } from 'react'

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => console.error(error), [error])
  return (
    <div className="max-w-[62ch] pt-16">
      <h1 className="statute text-[2.2rem] font-medium">Hakiki can’t reach its records right now</h1>
      <p className="mt-4 text-ink-2">
        The Acts and rulings come from a database that didn’t answer. Nothing you typed is lost. Try again in a moment.
      </p>
      {process.env.NODE_ENV === 'development' && (
        <p className="mt-3 text-sm text-ink-2">
          Running it locally? Start the API from the repo root with{' '}
          <code className="rounded bg-panel px-1.5 py-0.5 text-[0.9em]">uv run uvicorn api.main:app</code>.
        </p>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2">
        <button
          type="button"
          onClick={reset}
          className="min-h-11 rounded-md bg-ink px-5 py-2 font-medium text-paper transition-colors hover:bg-gazette"
        >
          Try again
        </button>
        <Link href="/" className="link inline-flex min-h-11 items-center">
          Back to the home page
        </Link>
      </div>
    </div>
  )
}
