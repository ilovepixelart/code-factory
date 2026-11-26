/** `value`, or a failure naming `what` when it is null or undefined. */
export function present<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`${what} is missing`)
  return value
}
