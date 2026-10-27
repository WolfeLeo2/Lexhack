import type { Metadata } from 'next'
import { IBM_Plex_Sans, Newsreader } from 'next/font/google'
import Link from 'next/link'
import { MobileMenu } from '@/components/MobileMenu'
import { SearchBox } from '@/components/SearchBox'
import { Seal } from '@/components/Seal'
import { THEME_SCRIPT, ThemeToggle } from '@/components/ThemeToggle'
import './globals.css'

const plex = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-plex' })
const newsreader = Newsreader({ subsets: ['latin'], style: ['normal', 'italic'], axes: ['opsz'], variable: '--font-newsreader' })

const NAV = [
  { href: '/acts', label: 'Acts' },
  { href: '/check', label: 'Check a filing' },
  { href: '/ask', label: 'Ask' },
  { href: '/about', label: 'About' },
]

const siteUrl =process.env.VERCEL_PROJECT_PRODUCTION_URL
  ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
  : process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:3000'

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: 'Hakiki: is this section still good law?', template: '%s · Hakiki' },
  description:
    'Hakiki checks Kenyan statutes against the court rulings that limited, upheld or struck them down, in the courts’ own words.',
  openGraph: {
    title: 'Hakiki: is this section still good law?',
    description:
      'Hakiki checks Kenyan statutes against the court rulings that limited, upheld or struck them down, in the courts’ own words.',
    siteName: 'Hakiki',
    locale: 'en_KE',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Hakiki: is this section still good law?',
    description:
      'Hakiki checks Kenyan statutes against the court rulings that limited, upheld or struck them down, in the courts’ own words.',
  },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: THEME_SCRIPT sets data-theme before React hydrates
    <html lang="en-KE" className={`${plex.variable} ${newsreader.variable} scroll-pt-20`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="paper-grain min-h-dvh">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:bg-paper focus:px-3 focus:py-2">
          Skip to content
        </a>
        <header className="sticky top-0 z-40 border-b border-rule bg-paper">
          <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-1.5 md:gap-6 md:px-8">
            <Link href="/" className="flex min-h-11 items-center gap-2.5" aria-label="Hakiki home">
              <Seal className="h-8 w-8 text-seal" />
              <span className="statute text-[1.4rem] leading-none font-medium tracking-[-0.01em]">Hakiki</span>
            </Link>
            <nav className="hidden gap-5 text-[0.95rem] text-ink-2 md:flex" aria-label="Main">
              {NAV.map((l) => (
                <Link key={l.href} href={l.href} className="inline-flex min-h-11 items-center whitespace-nowrap hover:text-ink">
                  {l.label}
                </Link>
              ))}
            </nav>
            <div className="ml-auto hidden w-full max-w-sm md:block">
              <SearchBox size="sm" />
            </div>
            <div className="hidden md:block">
              <ThemeToggle />
            </div>
            <MobileMenu links={NAV} />
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-5 sm:px-8">
          {children}
        </main>
        <footer className="mt-24 border-t border-rule">
          <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-x-10 gap-y-3 px-5 py-8 text-sm text-ink-2 sm:px-8">
            <p className="max-w-[70ch]">
              Hakiki reports what published sources say. It is not legal advice. Statute text comes from Kenya Law (CC
              BY-NC 4.0) via the Internet Archive; court rulings are quoted word for word, with a link to each judgment.
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
