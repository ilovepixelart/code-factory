// Changes through the write API: JSON in, the server's
// answer out; a refusal throws its reason, so every refusal can show.

import type { Changed } from '../generated/Changed'

/** A change the server refused, with the reason it gave. */
export class Refused extends Error {
  override name = 'Refused'
}

type Method = 'POST' | 'PATCH' | 'PUT' | 'DELETE'

/** What a request may add to asking for JSON. */
interface Asked {
  method?: Method
  headers?: Record<string, string>
  body?: string
  /** Ends the request when the read that sent it is overtaken or its page is left. */
  signal?: AbortSignal
}

/** Every request the app makes goes through here: JSON asked for, the caller's headers added. */
export function request(path: string, asked: Asked = {}): Promise<Response> {
  return fetch(path, { ...asked, headers: { Accept: 'application/json', ...asked.headers } })
}

/** What a change answers; `id` is the ticket a create or a duplicate made. */
export type Answered = Changed & { id?: string }

/** Send one change; a body is sent as JSON, and nothing is sent without one. */
export async function act(method: Method, path: string, body?: object): Promise<Answered> {
  const response = await request(
    path,
    body === undefined
      ? { method }
      : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  )
  const changed = (await answered(response)) as (Partial<Changed> & { id?: unknown }) | null
  const made = typeof changed?.id === 'string' ? { id: changed.id } : {}
  return { notice: changed?.notice ?? '', undo: changed?.undo ?? null, ...made }
}

/** Read the JSON at `path`; a refusal throws its reason, as a change's does. */
export async function ask<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await answered(await request(path, signal ? { signal } : {}))) as T
}

/** The JSON answer at `path`, or null when the board refuses; throws when it does not answer. */
export async function readJson<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  const response = await request(path, signal ? { signal } : {})
  return response.ok ? ((await response.json()) as T) : null
}

/** POST `body` as JSON and read the JSON answer; a refusal throws its reason. */
export async function post<T>(path: string, body: object): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return (await answered(response)) as T
}

async function answered(response: Response): Promise<unknown> {
  const answer: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new Refused(reasonOf(answer, response.status))
  return answer
}

/** The reason a refused answer gives: its problem `detail` (RFC 9457), else its status. */
export function reasonOf(answer: unknown, status: number): string {
  const detail = (answer as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' ? detail : `Refused (${String(status)})`
}
