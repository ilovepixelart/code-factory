<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import { computed } from 'vue'
import type { Card as BoardCard } from '../lib/board'
import { money, short, span } from '../lib/format'
import { doing, placeOf } from '../lib/session_view'
import type { Session, Usage } from '../lib/sessions'
import { ticketHref } from '../lib/ticket'
import CutText from './CutText.vue'
import StatusBadge from './StatusBadge.vue'
import { Button } from '@/components/ui/button'
import { Item, ItemActions, ItemContent, ItemDescription, ItemTitle } from '@/components/ui/item'

// A session waiting on the person (CF-1204): who it is, what it asks and how long it has waited,
// with Open session, where its terminal answers it. Only the longest wait takes the primary button.
const { session, usage, now, ticket, first } = defineProps<{
  session: Session
  usage: Usage | undefined
  now: number
  ticket: BoardCard | undefined
  first?: boolean
}>()
const ticketLink = computed(() => (ticket ? ticketHref(ticket.repository, ticket.id) : ''))
</script>

<template>
  <ContentCard role="listitem" :data-session="session.session_id">
    <Item class="py-3">
      <ItemContent class="min-w-0">
        <ItemTitle class="max-w-full min-w-0">
          <RouterLink
            v-if="ticket"
            :to="ticketLink"
            class="flex min-w-0 items-baseline gap-2 hover:underline"
            ><span class="shrink-0 font-mono text-muted-foreground">{{ ticket.id }}</span
            ><CutText :text="ticket.title"
          /></RouterLink>
          <span v-else class="truncate font-mono" :title="placeOf(session)">
            {{ placeOf(session) }}
          </span>
        </ItemTitle>
        <ItemDescription v-if="doing(session)" class="truncate" :title="doing(session)">
          {{ doing(session) }}
        </ItemDescription>
      </ItemContent>
      <ItemActions class="flex-wrap max-sm:basis-full">
        <StatusBadge state="blocked" />
        <span class="text-muted-foreground tabular-nums"
          >waiting {{ span(now - session.last_event_at) }} ·
          {{ typeof usage?.cost === 'number' ? money(usage.cost) : 'no cost yet' }}</span
        >
        <span class="font-mono text-muted-foreground">{{ short(session.session_id) }}</span>
        <Button
          as-child
          :variant="first ? 'default' : 'secondary'"
          :aria-label="`Open session ${short(session.session_id)}`"
          ><RouterLink :to="`/sessions/${session.session_id}`">Open session</RouterLink></Button
        >
      </ItemActions>
    </Item>
  </ContentCard>
</template>
