// The opening: the Penal Code as Kenya Law prints it today, and the margin note it's missing.
export function Hero() {
  return (
    <header className="grid grid-cols-1 gap-12 pt-10 pb-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16 lg:pt-14">
      <div className="max-w-[34rem] self-center">
        <p className="text-ink-2">LexHack 2026, explained for the team</p>
        <h1 className="statute mt-4 text-[2.6rem] leading-[1.08] font-medium tracking-[-0.02em] sm:text-[3.1rem]">
          Kenya's statute book doesn't say when a court has struck a section down.
        </h1>
        <p className="mt-6 text-lg text-ink-2">
          So lawyers, students and AI tools read laws that courts have already limited, and cite them as if nothing
          happened. LexHack reads the judgments and writes what each court did into the margin, in the court's own words.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <a href="#problem" className="rounded-md bg-ink px-4 py-2.5 font-medium text-paper hover:bg-gazette">
            Start reading
          </a>
          <a href="#try" className="rounded-md border border-rule px-4 py-2.5 font-medium hover:border-ink-2">
            Skip to the demo
          </a>
        </div>
      </div>

      <figure className="relative" aria-label="Penal Code section 204 as printed, with the missing court note">
        <div className="paper-grain relative rounded-sm border border-rule bg-[#fbfcf9] px-6 py-8 shadow-[0_1px_0_#c9d0c6,0_18px_40px_-24px_rgba(24,33,43,0.35)] sm:px-10 sm:py-10">
          <p className="statute text-center text-sm text-ink-2">Penal Code (Cap. 63), revised edition of 11 December 2023</p>
          <p className="statute mt-1 text-center text-sm text-ink-2">Part II, Chapter XVIII</p>
          <div className="statute mt-8 space-y-5 text-[1.12rem] sm:text-[1.25rem]">
            <p className="text-ink-2/70">
              <span className="font-semibold text-ink-2">203. Murder</span>
              <br />
              Any person who of malice aforethought causes death of another person by an unlawful act or omission is
              guilty of murder.
            </p>
            <p>
              <span className="font-semibold">204. Punishment of murder</span>
              <br />
              Any person convicted of murder{' '}
              <span className="hero-mark">shall be sentenced to death.</span>
            </p>
            <p className="text-ink-2/70">
              <span className="font-semibold text-ink-2">205. Punishment of manslaughter</span>
              <br />
              Any person who commits the felony of manslaughter is liable to imprisonment for life.
            </p>
          </div>
        </div>

        <aside className="hero-note relative z-10 -mt-10 ml-6 -rotate-[0.6deg] rounded-sm border border-seal/40 border-l-4 border-l-seal bg-paper p-4 shadow-[0_14px_30px_-18px_rgba(142,44,72,0.55)] sm:ml-20 sm:-mr-3">
          <p className="text-sm font-medium text-seal">Supreme Court, 14 December 2017</p>
          <p className="court mt-1.5 text-[1.02rem]">
            “The <span className="hl">mandatory nature of the death sentence</span> as provided for under section 204 of
            the Penal Code is hereby declared unconstitutional.”
          </p>
          <p className="mt-2 text-sm text-ink-2">
            Muruatetu v Republic, para 112(a). Six years later, the printed text still hasn't changed.
          </p>
        </aside>
      </figure>
    </header>
  )
}
