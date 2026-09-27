'use client'

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="max-w-[62ch] pt-16">
      <h1 className="statute text-[2.2rem] font-medium">The citator’s database didn’t answer</h1>
      <p className="mt-4 text-ink-2">
        Hakiki couldn’t reach its API, or the API couldn’t reach the database. Running it locally? Start the API from
        the repo root with <code className="rounded bg-panel px-1.5 py-0.5 text-[0.9em]">uv run uvicorn api.main:app</code>,
        then try again.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-md bg-ink px-4 py-2 font-medium text-paper transition-colors hover:bg-gazette"
      >
        Try again
      </button>
    </div>
  )
}
