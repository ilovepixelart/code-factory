import { createSharedComposable, useIntervalFn, useTimestamp } from '@vueuse/core'
import { STAGE_LABELS, type Card, type Pull } from './board'

export const useDeliveryClock = createSharedComposable(() =>
  useTimestamp({ scheduler: (tick) => useIntervalFn(tick, 1000) }),
)

interface DeliveryStatus {
  label: string
  /** The status word its tone is read by when the label names an agent (`statusTone`). */
  state?: string
  since?: number | undefined
  retryAt?: number
}

function runStatus(card: Card): DeliveryStatus | null {
  const run = card.runs.at(-1)
  if (!run) return card.holder ? { label: `${card.holder} working`, state: 'working' } : null
  // An empty agent name falls through to the holder like a missing one.
  const agent = [run.agent, card.holder].find(Boolean) ?? 'Agent'
  return {
    label: `${agent} · ${STAGE_LABELS[run.stage]}`,
    state: 'working',
    ...(run.started_at ? { since: run.started_at } : {}),
  }
}

function eventStatus(event: Card['delivery_event']): DeliveryStatus | null {
  if (event?.kind === 'ship_failed' || event?.kind === 'merge_failed') {
    const action = event.kind === 'ship_failed' ? 'Ship' : 'Merge'
    return event.retry_at === null
      ? { label: `${action} failed` }
      : { label: `${action} interrupted`, retryAt: event.retry_at }
  }
  const since = event?.at ?? undefined
  if (event?.kind === 'ship_started') return { label: 'Shipping branch', since }
  if (event?.kind === 'ship_pushed') return { label: 'Opening pull request', since }
  return null
}

function pullStatus(card: Card, pull: Pull, since: number | undefined): DeliveryStatus | null {
  if (pull.conflict) return { label: 'Merge conflict' }
  if (pull.draft) return null
  const entered = Number(pull.since ?? pull.at) || since
  const other = pull.other_ci ?? pull.ci
  if (card.check?.passed === false || other === 'failed') return { label: 'Checks failed' }
  if (other === 'pending' || (card.check === null && card.checks_configured)) {
    return { label: 'Waiting for checks', since: entered }
  }
  return null
}

function shippingStatus(card: Card): DeliveryStatus | null {
  const pull = card.pull
  if (pull?.state === 'merged' || pull?.state === 'closed') return null
  const event = card.delivery_event
  const status =
    eventStatus(event) ??
    (pull?.state === 'open' ? pullStatus(card, pull, event?.at ?? undefined) : null)
  if (status) return status
  return card.queue === 'next' ? { label: 'Queued for an agent' } : null
}

export function deliveryStatus(card: Card): DeliveryStatus | null {
  if (card.stage === 'merged' || card.stage === 'released' || card.archived) return null
  if (card.open_questions) return { label: 'Waiting for an answer' }
  if (card.runs.length || card.holder) return runStatus(card)
  return shippingStatus(card)
}
