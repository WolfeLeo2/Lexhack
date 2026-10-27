// Fallback while a page waits on the API (the section page has its own, shaped like itself).
export default function Loading() {
  const bar = 'animate-pulse rounded-sm bg-panel motion-reduce:animate-none'
  return (
    <div className="pt-12" aria-busy="true">
      <p className="sr-only" role="status">
        Loading
      </p>
      <div className={`${bar} h-12 w-2/3 max-w-xl`} />
      <div className={`${bar} mt-6 h-5 w-full max-w-2xl`} />
      <div className={`${bar} mt-3 h-5 w-4/5 max-w-xl`} />
      <div className={`${bar} mt-10 h-40 w-full max-w-4xl`} />
    </div>
  )
}
