// Where delivery stands on the ticket page: a failed ship or merge with its reason, and what a
// merge at Review waits on. Pure, so the Status and Agent sections read one rule.

import type { Card } from './board'
import { span } from './format'

type Event = Card['delivery_event']

/** The delivery step that failed: `ship`, `merge`, or '' while none did. */
export function failedStep(event: Event): '' | 'ship' | 'merge' {
  if (event?.kind === 'ship_failed') return 'ship'
  return event?.kind === 'merge_failed' ? 'merge' : ''
}

/** `Ship failed 2m ago: <reason>`, from the failure's record and the time now (epoch seconds). */
export function failureWords(event: Event, now: number): string {
  const step = failedStep(event)
  if (!step || !event) return ''
  const ago = event.at === null ? '' : ` ${span(Math.max(0, now - event.at))} ago`
  const why = event.reason ? `: ${event.reason}` : ''
  return `${step === 'ship' ? 'Ship' : 'Merge'} failed${ago}${why}`
}

export interface MergeItem {
  done: boolean
  text: string
}

function checkItem(check: Card['check'], configured: boolean): MergeItem {
  if (!check) {
    return configured
      ? { done: false, text: 'Waiting for checks' }
      : { done: true, text: 'No board checks to wait for' }
  }
  const words = check.passed ? 'passed' : 'failed'
  return { done: check.passed, text: `Checks ${words} on ${check.commit.slice(0, 7)}` }
}

/** What the merge of an open pull request waits on, each ticked or open. */
export function mergeItems(card: Card, findingsOpen: number): MergeItem[] {
  const pull = card.pull
  if (pull?.state !== 'open') return []
  const ci = pull.ci === 'passed' || pull.ci === 'none' || !pull.ci
  return [
    pull.draft
      ? { done: false, text: 'Pull request is a draft' }
      : { done: true, text: 'Pull request open' },
    checkItem(card.check, Boolean(card.checks_configured)),
    { done: ci, text: ci ? 'CI passed' : `CI ${pull.ci}` },
    findingsOpen
      ? { done: false, text: `${String(findingsOpen)} review findings open` }
      : { done: true, text: 'No open review findings' },
  ]
}
