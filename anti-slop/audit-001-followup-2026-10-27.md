# Follow-up to audit 001: HIGH items (#1 to #8)

Approved: all HIGH findings, plus browser verification of anything that needed it. MEDIUM and LOW items (#9 onward) were not touched.

Verification: local `next dev` against the live API, driven by headless Chromium (Playwright; the Chrome extension tools were not available in this session). `tsc --noEmit` and `eslint` are clean. Widths tested: 360, 375, 640, 768, 820, 1024, 1280.

| # | Result | Evidence |
|---|---|---|
| 1 Em dashes | Fixed | `AnswerView.tsx` strings now use a colon. `grep` for the character in `app/` and `components/` finds none. `lib/text.ts` left alone (statute text repair, your call). |
| 2 Focus | Fixed | Removed `outline-none` from lineage nodes and Acts shelf links; both now show the 2px gazette outline (computed `solid 2px rgb(30,91,71)`, screenshot checked). Filing sheet gets a 2px gazette ring on `:focus-within` (computed box-shadow confirmed). |
| 3 Tap targets | Fixed | Probe at 375px over `/`, `/check`, `/ask`, `/about`, `/acts`, `/search`, a section page: before, home example tabs (34px) and section breadcrumbs (20px) failed; after, none under 44px. Header nav, theme toggle, search, Ask buttons, mode toggle, chips, send, copy/Word/PDF, history Close / New chat, error buttons all `min-h-11` or larger. |
| 4 Header on phones | Was a real bug, fixed | Before: at 360px the page was 415px wide and the theme toggle sat at x 379 to 415 (off-screen). After: no horizontal overflow on any route at any tested width. Below 768px the header is logo, search icon and a labelled **Menu** button; the panel holds the four links and "Switch to dark theme". Verified: opens, `aria-expanded`, link navigates and closes it, Escape closes and returns focus to Menu, outside tap closes, theme flips and persists after reload. 768px desktop layout fits (search 236px, toggle ends at x 736). |
| 5 Upload button | Was a real bug, fixed | Before: at 375px the button was at x 817 to 1016. After: "Upload PDF or DOCX" is first and full width (x 20 to 355); the exhibit tabs wrap under a "Synthetic examples" line instead of scrolling. Same order on desktop (upload, label, Exhibits A to C), so DOM order matches visual order. |
| 6 States | Fixed | `loadExhibit`: checks `res.ok`, try/catch; a forced 404 left the textarea unchanged and showed "Couldn't load that example". `readFile`: try/catch; an aborted server action cleared the "Reading" overlay and showed a message. New `app/loading.tsx` for pages without their own. `app/error.tsx` now speaks to visitors, logs the error, links home; the `uv run uvicorn` hint shows only in development. Not changed: an unknown section id still returns HTTP 200 in dev (the existing `loading.tsx` streams before `notFound()`), which I did not investigate. |
| 7 Claims | Fixed or confirmed | `/check`: "Nothing is stored" now reads "Hakiki reads your text or file, checks it against its records and discards it. It does not save either." I grepped `api/` for storage and logging of filings and found none (only judgment text is cached), but host-level logs at Vercel or Railway were not checked. `/ask`: now says the question goes to Google's Gemini model and to leave out anything confidential (the agent calls the Gemini API per `api/agent.py`). About: "every ruling it accepted" is now "all 59 rulings it accepted". Footer licence: left as is; `README.md:187` and `crawler/REPORT.md:192` record CC BY-NC 4.0 as binding (checked in the repo, not on the live site). |
| 8 Click-through | Done for what was run | Interactions exercised: Menu open, close (Escape, outside tap, link), theme toggle and persistence, exhibit tab load, forced exhibit 404, forced upload failure, textarea focus, keyboard focus on lineage and shelf. Console errors: only the two I caused (the stubbed 404 and the aborted request). Not exercised: a real PDF/DOCX upload, Ask streaming and its Copy/Word/PDF buttons, the History sheet (they need the model and a chat); their size changes were checked in code only. |

Changed files: `app/about/page.tsx`, `app/ask/{AnswerView,Ask,History,page}.tsx`, `app/check/{Checker,page}.tsx`, `app/error.tsx`, `app/layout.tsx`, `app/loading.tsx` (new), `app/p/[...id]/page.tsx`, `components/{Lineage,MobileMenu (new),Specimen,ThemeToggle,illustrations}.tsx`.

---

# Round 2 (same day): changes to round 1, then MEDIUM items #9 to #15

Changes you asked for:
- Hamburger is icon only (`aria-label="Menu"`, 44px, no visible word).
- Exhibits scroll sideways again on phones (examples scroller `overflow-x: auto`, 335px visible of 775px). The upload button stays outside the scroller, so it is always visible.

| # | Result |
|---|---|
| 9 Contrast | Placeholders now `text-ink-2` (6.33:1 light, 7.95:1 dark; was 3.24:1). New `--color-edge` token for the border of anything you type in: 3.35:1 light (#788690), 3.82:1 dark (#6a7782). Applied to the search box, section filter, Ask composer and the filing sheet. |
| 10 Icons | `Sparkles` fallback removed (unknown tool steps use the Search icon). Library migration: see the answer in chat; not done. |
| 11 Crimson | About glossary labels and benchmark scores are ink now; the Ask disclaimer stripe is gone. Seal remains for "a court acted", flagged citations and errors. |
| 12 Motion | Checker's spinning icon replaced by the text "Checking" with three dots that light in turn (`.dots`, static under reduced motion; verified `animation-name: none` with reduced motion on). No other un-guarded `animate-*` remains outside `motion-safe:` / `motion-reduce:`. The hand-kept reduced-motion list was left as is. |
| 13 Ask look | Round send arrow became a rectangular "Ask" / "Draft" button; chips and the Answer/Draft toggle are square-cornered like the rest of the site. Composer gets a visible border and focus ring. |
| 14 Shadows | `--shadow-rgb` per theme (light 24 33 43, dark 0 0 0); 9 hard-coded shadows now use it. |
| 15 Controls | Exercised against a local API: real PDF upload (901 chars read), real DOCX upload (1,299 chars), Ask streaming (answer in 9 s, two steps shown), Word export (38 KB .docx), PDF export (27 KB .pdf), history sheet opens, Close is 44px, Escape closes it, New chat, Draft toggle. Console errors: none. |

---

# Round 3: Hugeicons and the Answer/Draft switch

- **Icons:** all 25 Lucide icons replaced with Hugeicons (`@hugeicons/react` + `@hugeicons/core-free-icons`); `lucide-react` removed from `web/package.json`. Every icon goes through `components/Glyph.tsx` (stroke weight set once, 1.5). I checked the chosen exports are native Hugeicons designs (1.5 stroke, bezier paths), not Lucide copies. Rendered and checked: header, mobile menu, section page links, Ask steps and action buttons.
- **Ask controls:** round send arrow, pill chips and pill toggle are back (the field border and 44px sizes from round 2 stay).
- **Mode switch:** a second copy of the labels in the active colours is clipped to the chosen half (`clip-path: inset(...) round`), so the pill slides and the text colour changes in one movement. 240ms, `cubic-bezier(0.77, 0, 0.175, 1)`; instant under reduced motion. Sampled mid-transition: the clip eases across (about 0, 2, 7, 38, 46, 50 percent over six frames). Keyboard (Enter on a focused half) works; both halves are 87 by 44px.
- **Side fix:** the global `:focus-visible` rule set `border-radius: 2px` on every focused element, which squared off focused pills (toggle, chips, send button). It now applies only to `a.link`.
- **Focus outline on the pill, checked by screenshot:** the 2px outline follows the pill in all four states (Answer or Draft selected and focused, light and dark theme) and stays visible against both the dark and light pill. No further change was needed.
