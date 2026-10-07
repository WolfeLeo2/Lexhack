# Review: /ask session storage + chat history (b2b6dd5, Leo)

Reviewed from code (no browser tools in this session; dev server and API were up, but nothing to screenshot with).
B = would block a merge. U = UX rough edge. Everything below is fixed in the following commits unless marked "kept".

## State and storage
- B1 **Every streamed chunk rewrites localStorage.** `delta`/`step` patches change `sessions`, and the sync effect
  stringifies up to 25 whole sessions (parts, rulings, check lists) and calls `setItem` on each one: dozens of
  synchronous 100 KB+ writes a second while an answer streams. Persist only when no turn is streaming.
- B2 **Quota errors are swallowed.** `setItem` throws `QuotaExceededError` (5 MB; long drafts with check lists add up),
  the catch drops it, and *nothing* is saved from then on while the page still says chats are saved. Drop the oldest
  chats until it fits; if even one doesn't fit (or storage throws: Safari private mode, storage disabled), say so.
- B3 **No schema version.** Stored turns are the stream contract's `Answer`/`Part` shapes; when the contract changes,
  old chats render garbage or crash `toLines`. Key the store by version (`hakiki:ask:v1`) and drop records that don't
  validate (sessions without an id/turns array, turns without a question).
- U1 Hydration: no mismatch (SSR renders the empty state, restore runs in an effect), but the empty state with the
  example chips paints, then jumps to the restored chat. Render nothing for the conversation until restored.
- U2 Multiple tabs: each tab writes its whole array, last writer wins, so a chat asked in tab A disappears when tab B
  saves. Listen to the `storage` event and take the other tab's list (it is the newer one).
- U3 `crypto.randomUUID()` only exists in secure contexts: on `http://192.168.x.x:3000` (testing on a phone) asking
  throws before the request is sent. Use a time+random id.
- U4 Titles are cut with `slice(0, 52)` (can split a surrogate pair) on top of CSS clamping. Store the question; let
  CSS truncate. Sessions keep creation order, so a chat you continue stays buried; sort by last update.
- U5 `useEffect(..., [activeId])` reads `activeSession` without listing it (lint warning); the session `mode` is the
  first turn's mode, so the header says "Draft submission" for a chat that later asked plain questions. Drop the
  session-level mode; label by what the chat contains.

## Streaming
- B4 **Retry appends instead of replacing.** `retry(i)` calls `ask(q, turns.slice(0, i))`, which appends a new turn at
  `turns.length` but `patch` writes to index `i` (= `prior.length`, the failed turn). The answer streams into the old
  turn and the new one stays `pending: true` forever, which also disables the send button for that chat.
- B5 **An aborted turn stays pending forever.** "New inquiry", switching chats or deleting the active one aborts the
  stream; the catch returns early (`ctrl.signal.aborted`), the turn keeps `pending: true`, and going back to that
  chat shows "Reading your question" pulsing with the send button disabled. Mark it stopped, with "Ask again".
- B6 **A reload mid-answer stores a turn with no answer and no error.** Saving sets `pending: false, live: []`, so the
  restored chat shows a question with nothing under it and no way to ask again. Store it as interrupted (error text +
  Ask again). `delta` text is correctly never stored as an answer (kept).

## History sent to the API
- Kept: `prior.filter(answer).slice(-6)`, answers sliced to 4000 chars, questions ≤ 2000 (the API's limits).
  Restored chats send the same history. Turns that errored are skipped.

## Privacy
- U6 Where chats are kept is said only on the empty state ("browser's local records"). Say it plainly and in one place
  that's always visible: kept only in this browser; nothing is stored by Hakiki; the last few questions and answers go
  with a follow-up as context.
- U7 "Clear register" deletes every chat in one click with no confirmation or undo; per-chat "Remove" too. Fixed with
  Undo instead of a confirm: removing one chat or all of them shows "Removed …  Undo" (focus moves to Undo), one
  mechanism for both.

## Accessibility
- B7 **Nested interactive controls.** Each history row is a `div role=button` containing a `<button>Remove`. Keyboard:
  Enter on Remove bubbles to the row's `onKeyDown`, which calls `preventDefault()` (so the button's click never fires)
  and opens the chat instead. Remove is unreachable by keyboard. Make the row a real button and Remove a sibling.
- B8 **The drawer is a fake modal.** `role=dialog aria-modal` on a div: focus isn't moved into it, isn't trapped,
  isn't restored to the opener, and the page behind stays tabbable. Use a native `<dialog>` + `showModal()` (focus,
  Escape, inert background for free).
- U8 Drawer "Remove" is `opacity-0` until hover: invisible on touch screens. Always visible, quiet.
- U9 The conversation header `<h2>` repeats the question already shown in the first bubble.

## UX (read as a designer)
- U10 Two different history UIs: a full-width ledger on the empty page and a drawer in a chat, with different row
  layouts, and the drawer button only appears with 2+ chats (with one saved chat, open, there is no history control at
  all). One list component, used in both places; the history button always shown when there is any history.
- U11 Vocabulary drifts: "Ask Hakiki", "Legal inquiry", "Inquiry register", "Register (3)", "Previous inquiries",
  "Open →". "Legal inquiry" reads like a consultation (we don't give advice). Use "Your questions" / "Earlier chats",
  "New chat", "Answer"/"Draft" (the toggle's words).
- U12 Long titles: `line-clamp-1` on a flex-wrap row pushes the Draft tag to its own line; drawer rows truncate but the
  timestamp row is fine. Title in its own clamped block, tag + meta beneath.
- U13 "New inquiry" while an answer is streaming silently throws the answer away. Disable it while streaming or say
  the answer stops; we mark the turn "Stopped" (B5), so it is recoverable.
- U14 The scroll-to-last-turn effect fires on reopening a chat and on reload (turns.length changes), yanking the page
  past the heading. Scroll only when a question is asked.
- U15 Answers have no Copy (drafts do) and nothing to take an answer away in a document (section 3 adds Word/PDF).
- U16 Ask.tsx is ~900 lines: storage, history UI, composer and answer rendering in one file. Split into
  `useChats.ts` (storage), `History.tsx`, `AnswerView.tsx` (answer/draft/ruling rendering).
- Consistent with the site (kept): `statute` serif, `border-rule` hairlines, `note` panels for errors, no verdict
  colours. The drawer's hard shadow and `paper-grain` match `/check`'s exhibits.
