<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import {
  BotIcon,
  Clock01Icon,
  ComputerTerminal01Icon,
  GitBranchIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { Card } from '../lib/board'
import { clock, count, money, short, span, trim } from '../lib/format'
import { placeOf, rowLine } from '../lib/session_view'
import type { Session, Usage } from '../lib/sessions'
import { ticketHref } from '../lib/ticket'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'
import CutText from './CutText.vue'
import PullLabel from './PullLabel.vue'
import StatusBadge from './StatusBadge.vue'

// A session as one compact row (CF-1204): state, its ticket (else repository and branch), what it
// is doing now, its age and cost. The session link stretches over the row; the ticket link sits
// above it. Under its repository's heading (`grouped`) the place is the branch alone. The open
// tool call and the subagents show on expand.
const { session, usage, now, ticket, grouped } = defineProps<{
  session: Session
  usage: Usage | undefined
  now: number
  ticket: Card | undefined
  grouped?: boolean
}>()
const running = computed(() => session.subagents.filter((a) => a.running))
const finished = computed(() => session.subagents.filter((a) => !a.running).length)
const ticketLink = computed(() => (ticket ? ticketHref(ticket.repository, ticket.id) : ''))
const cost = computed(() => usage?.cost ?? null)
const subagentLine = (a: Session['subagents'][number]): string =>
  `${a.agent_type || 'subagent'} ${short(a.agent_id)} · ${a.stale ? 'stale' : 'running'}` +
  (a.current_action && !a.stale
    ? ` · ${a.current_action.tool} ${trim(a.current_action.summary, 80)}`
    : '')
const expandable = computed(() => session.current_action !== null || session.subagents.length > 0)
</script>

<template>
  <ContentCard role="listitem" :data-session="session.session_id">
    <Item class="relative py-3">
      <ItemMedia><StatusBadge :state="session.stale ? 'stale' : session.state" /></ItemMedia>
      <ItemContent class="min-w-0">
        <ItemTitle class="line-clamp-none flex-wrap">
          <RouterLink
            v-if="ticket"
            :to="ticketLink"
            class="relative flex min-w-0 max-w-full items-baseline gap-2 hover:underline"
            ><span class="font-mono shrink-0 text-sm text-muted-foreground">{{ ticket.id }}</span
            ><CutText class="font-medium" :text="ticket.title"
          /></RouterLink>
          <PullLabel v-if="ticket" :card="ticket" />
          <span v-else class="font-mono flex min-w-0 items-center gap-1 text-sm"
            ><HugeiconsIcon
              :icon="GitBranchIcon"
              class="size-3.5 shrink-0"
              aria-hidden="true" /><CutText
              :text="grouped ? session.branch || 'no branch' : placeOf(session)"
          /></span>
          <RouterLink
            :to="`/sessions/${session.session_id}`"
            :aria-label="`Session ${short(session.session_id)}`"
            class="text-muted-foreground text-sm after:absolute after:inset-0 hover:text-foreground"
            >session <span class="font-mono">{{ short(session.session_id) }}</span></RouterLink
          >
        </ItemTitle>
        <ItemDescription
          v-if="rowLine(session, now)"
          class="truncate"
          :title="rowLine(session, now)"
        >
          {{ rowLine(session, now) }}
        </ItemDescription>
      </ItemContent>
      <ItemActions class="text-muted-foreground tabular-nums max-sm:basis-full">
        <span
          :title="
            cost !== null
              ? 'Reported by the agent runtime'
              : 'The runtime has not reported a cost for this session yet'
          "
          ><template v-if="cost === null">no cost yet</template
          ><template v-else
            ><span class="font-medium text-muted-foreground">{{ money(cost) }}</span
            ><template v-if="usage?.cost_incomplete"> incomplete</template></template
          ><template v-if="usage?.output"> · {{ count(usage.output) }} out</template></span
        >
        <span class="flex items-center gap-1"
          ><HugeiconsIcon
            :icon="Clock01Icon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          /><template v-if="session.state === 'blocked'"
            >waiting {{ span(now - session.last_event_at) }}</template
          ><template v-else-if="session.state === 'ended'"
            >ended {{ clock(session.last_event_at) }}</template
          ><template v-else>{{ span(now - session.last_event_at) }} ago</template></span
        >
      </ItemActions>
      <ItemFooter v-if="expandable">
        <Collapsible :unmount-on-hide="false" class="relative w-full">
          <CollapsibleTrigger as-child
            ><Button type="button" variant="ghost" size="xs"
              >Tool call and subagents</Button
            ></CollapsibleTrigger
          >
          <CollapsibleContent>
            <p
              v-if="session.current_action"
              class="font-mono text-xs mt-1.5 flex items-center gap-2 rounded-md bg-muted px-2.5 py-1.5"
              :title="session.current_action.summary"
            >
              <HugeiconsIcon
                :icon="ComputerTerminal01Icon"
                class="size-3.5 text-muted-foreground shrink-0"
                aria-hidden="true"
              /><CutText class="font-semibold" :text="session.current_action.tool" />
              <span class="min-w-0 flex-1 truncate text-muted-foreground">{{
                trim(session.current_action.summary, 160)
              }}</span>
              <span class="text-muted-foreground shrink-0">{{
                span(now - session.current_action.started_at)
              }}</span>
            </p>
            <div
              v-if="session.subagents.length"
              class="mt-2 ml-1 grid gap-0.5 border-l border-border pl-3"
            >
              <p
                v-for="a in running"
                :key="a.agent_id"
                class="font-mono text-sm flex min-w-0 items-center gap-1.5"
              >
                <HugeiconsIcon
                  :icon="BotIcon"
                  class="size-3.5 shrink-0 text-foreground"
                  aria-hidden="true"
                /><CutText :text="subagentLine(a)" />
              </p>
              <p v-if="finished" class="font-mono text-sm text-muted-foreground">
                {{ finished }} subagent{{ finished !== 1 ? 's' : '' }} finished
              </p>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </ItemFooter>
    </Item>
  </ContentCard>
</template>
