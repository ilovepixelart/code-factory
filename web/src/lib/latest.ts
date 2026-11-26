// Overlapping reads where only the latest may apply its answer: each read takes a token, and an
// answer whose token is no longer the latest is dropped, however late it arrives.

/** A source of tokens; `take()` starts a read and returns whether it is still the latest. */
export function latest(): { take: () => () => boolean } {
  let last = 0
  return {
    take() {
      const mine = ++last
      return () => mine === last
    },
  }
}
