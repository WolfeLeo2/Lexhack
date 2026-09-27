// The API takes most of a second from Kenya (Neon is in Frankfurt): show the page's shape while it answers.
export default function Loading() {
  const bar = 'animate-pulse rounded-sm bg-panel motion-reduce:animate-none'
  return (
    <div className="pt-8" aria-busy="true" aria-label="Loading section">
      <div className={`${bar} h-4 w-48`} />
      <div className="mt-8 grid grid-cols-1 gap-14 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          <div className={`${bar} h-5 w-40`} />
          <div className={`${bar} mt-3 h-12 w-3/4`} />
          <div className={`${bar} mt-8 h-36 w-full`} />
        </div>
        <div className={`${bar} h-20 w-64 lg:mt-16`} />
      </div>
    </div>
  )
}
