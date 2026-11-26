<script setup lang="ts">
import SectionCard from './SectionCard.vue'
import { computed } from 'vue'
import type { Card as BoardCard } from '../lib/board'
import { clock, count, money, span } from '../lib/format'
import type { Session, Usage } from '../lib/sessions'
import { ticketHref } from '../lib/ticket'
import CutText from './CutText.vue'
import StatusBadge from './StatusBadge.vue'

// A session's facts at the top of its page: state, ticket, branch, the cost and tokens its runtime
// reported, its last event and its id.
const { usage } = defineProps<{
  session: Session
  ticket: BoardCard | undefined
  usage: Usage | null
  now: number
}>()

const cost = computed(() => usage?.cost ?? null)
const tokens = computed(() => {
  const u = usage
  if (!u) return []
  const all: [number, string][] = [
    [u.input, 'in'],
    [u.output, 'out'],
    [u.cache_read, 'cache read'],
    [u.cache_write, 'cache write'],
  ]
  return all.filter(([value]) => value)
})
</script>

<template>
  <SectionCard class="mb-6" heading="session-facts-heading" title="Session">
    <dl class="grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg bg-muted p-4 text-sm md:grid-cols-4">
      <div>
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">State</dt>
        <dd class="mt-1 flex items-center gap-2">
          <StatusBadge :state="session.stale ? 'stale' : session.state" />
        </dd>
      </div>
      <div v-if="ticket" class="col-span-2 min-w-0 md:col-span-3">
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">Ticket</dt>
        <dd class="mt-1 min-w-0">
          <RouterLink
            :to="ticketHref(ticket.repository, ticket.id)"
            class="flex min-w-0 items-baseline gap-2 hover:underline"
            ><span class="font-mono text-sm shrink-0 text-muted-foreground">{{ ticket.id }}</span>
            <CutText class="font-medium" :text="ticket.title"
          /></RouterLink>
        </dd>
      </div>
      <div v-if="session.branch" class="min-w-0">
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">Branch</dt>
        <dd class="font-mono text-sm mt-1 truncate" :title="session.branch">
          {{ session.branch }}
        </dd>
      </div>
      <div>
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">Cost</dt>
        <dd class="mt-1 tabular-nums">
          <span v-if="cost === null" class="text-muted-foreground">cost not reported yet</span
          ><template v-else
            ><span class="font-medium">{{ money(cost) }}</span> reported at
            {{ clock(usage?.reported_at ?? 0)
            }}<template v-if="usage?.cost_incomplete">, cost incomplete</template></template
          >
        </dd>
      </div>
      <div>
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">Tokens</dt>
        <dd class="mt-1 tabular-nums" title="Tokens in the transcripts, subagents included">
          <template v-for="([value, kind], i) in tokens" :key="kind"
            >{{ count(value) }} {{ kind }}{{ i < tokens.length - 1 ? ' · ' : '' }}</template
          ><span v-if="!tokens.length" class="text-muted-foreground">none yet</span>
        </dd>
      </div>
      <div>
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          Last event
        </dt>
        <dd class="mt-1 tabular-nums">
          {{
            session.state === 'ended'
              ? `ended ${clock(session.last_event_at)}`
              : `${span(now - session.last_event_at)} ago`
          }}
        </dd>
      </div>
      <div class="col-span-2 min-w-0">
        <dt class="text-xs font-medium tracking-wider text-muted-foreground uppercase">Session</dt>
        <dd class="font-mono text-sm mt-1 break-all">{{ session.session_id }}</dd>
      </div>
    </dl>
  </SectionCard>
</template>
