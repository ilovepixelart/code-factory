<script setup lang="ts">
import { Badge } from '@/components/ui/badge'
import AgentCardMenu from './AgentCardMenu.vue'
import { computed, ref } from 'vue'
import type { AgentDefinition } from '../generated/AgentDefinition'
import type { ModelCheck } from '../generated/ModelCheck'
import { act } from '../lib/actions'
import { STAGE_LABELS, type Stage } from '../lib/board'
import { confirm } from '../lib/confirm'
import { needsAttention, type Reach } from '../lib/connections'
import { dayClock, hourMinute, localDay, resumes, span } from '../lib/format'
import { refusalText, useAction } from '../lib/notice'
import {
  agentState,
  bodyOf,
  draftOf,
  limitsText,
  metersOf,
  takesText,
  tokensLater,
  type AgentDraft,
  type Doing,
  type Gap,
  type Last,
} from '../lib/roster'
import { ticketHref } from '../lib/ticket'
import AgentContextLine from './AgentContextLine.vue'
import AgentMeters from './AgentMeters.vue'
import AgentForm from './AgentForm.vue'
import ContentCard from './ContentCard.vue'
import { CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { BotIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { statusWord, type BadgeTone } from '../lib/status_tone'
import StatusBadge from './StatusBadge.vue'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'

// One defined agent as a card: what it is doing, what it runs and where, the same rows on every
// card, and while it holds a ticket a meter per limit; Edit opens its form in place across the
// grid's row, Remove takes it out. `reach` is what the page's connection check says of its
// connection; Check asks the page to check again. `modelCheck` is its model's last check (CF-401),
// shown with Test model on a card whose connection is on this machine (`local`).
const props = defineProps<{
  agent: AgentDefinition
  doing: Doing | undefined
  last: Last | undefined
  modelCheck: ModelCheck | undefined
  local: boolean
  now: number
  runtimes: string[]
  gaps: Record<string, Gap[]>
  roles: Stage[]
  connections: string[]
  models: Record<string, string[]>
  reach: Reach
  checking: boolean
}>()
const emit = defineEmits<{ changed: []; check: [] }>()

// The badge tone of each state the card shows, from the one tone table every badge uses.
const STATE_TONE = {
  idle: 'quiet',
  working: 'info',
  waiting: 'warning',
  'over limit': 'error',
  paused: 'quiet',
  'check failed': 'error',
  'usage limit': 'warning',
} as const satisfies Record<string, BadgeTone>

const editing = ref(false)
const { busy, error, send: sendTo } = useAction()
const testing = ref(false)
const address = computed(() => `/api/agent-definitions/${encodeURIComponent(props.agent.name)}`)
const paused = computed(() => props.agent.paused_at !== undefined)
const state = computed(
  () =>
    agentState(props.agent, props.doing, props.last, props.modelCheck) as keyof typeof STATE_TONE,
)
const stateTone = computed((): BadgeTone => STATE_TONE[paused.value ? 'paused' : state.value])
// A connection that answers is green, one that does not is red, any other trouble amber.
const reachTone = computed((): BadgeTone => {
  if (props.reach === 'answers') return 'success'
  if (props.reach === 'does not answer') return 'error'
  return needsAttention(props.reach) ? 'warning' : 'quiet'
})
// One action at a time on an agent: a change being sent or its model being tested (CF-480).
const locked = computed(() => busy.value || testing.value)
const meters = computed(() => metersOf(props.agent, props.doing))
const later = computed(() => tokensLater(props.agent, props.doing))
const lacks = computed(() => props.gaps[props.agent.runtime] ?? [])
// CF-1065: a local server holds no harness default model, so a local agent needs its own.
const modelTone = computed(() => {
  if (props.agent.model) return 'font-mono text-sm text-muted-foreground'
  return props.local ? 'text-foreground' : 'text-muted-foreground'
})
const modelText = computed(
  () =>
    props.agent.model ||
    (props.local ? 'no model: a local connection needs one' : 'harness default'),
)
// `HH:MM` for a pause today, with its day before that (CF-480).
const pausedAt = computed(() => {
  const at = props.agent.paused_at
  if (at === undefined) return ''
  return localDay(at) === localDay(props.now) ? hourMinute(at) : dayClock(at, props.now)
})

async function send(method: 'PATCH' | 'DELETE', body?: object): Promise<void> {
  await sendTo(method, address.value, body, () => {
    editing.value = false
    emit('changed')
  })
}

// Removing an agent takes it out of the run order: it asks first, as deleting a ticket does.
async function remove(): Promise<void> {
  if (await confirm(props.agent.name, { title: 'Remove agent', verb: 'Remove' })) {
    await send('DELETE')
  }
}

async function testModel(): Promise<void> {
  testing.value = true
  error.value = ''
  try {
    await act('POST', `${address.value}/model-check`)
    emit('changed')
  } catch (error_) {
    error.value = refusalText(error_)
  }
  testing.value = false
}

// Pause stays focusable while its own change is sent (`aria-disabled`, not `disabled`), so
// keyboard focus is not dropped to the page; a press in that time does nothing.
function togglePause(): void {
  if (locked.value) return
  void send('PATCH', { paused: !paused.value })
}

function open(): void {
  error.value = ''
  editing.value = true
}

function save(draft: AgentDraft): void {
  void send('PATCH', bodyOf(draft))
}

// Restore keeps the form open: its area takes the restored text once the board took it (CF-1163).
const restore = async (at: number): Promise<boolean> => {
  await sendTo('POST', `${address.value}/context/restore`, { at }, () => {
    emit('changed')
  })
  return error.value === ''
}
</script>

<template>
  <ContentCard role="listitem" size="sm" :aria-label="agent.name">
    <CardContent v-if="editing" class="min-w-0">
      <AgentForm
        :name="`Edit ${agent.name}`"
        :start="draftOf(agent)"
        :runtimes="runtimes"
        :gaps="gaps"
        :roles="roles"
        :connections="connections"
        :models="models"
        submit="Save"
        :error="error"
        :busy="busy"
        :history="agent.context_history ?? []"
        :now="now"
        :restore="restore"
        @save="save($event)"
        @cancel="editing = false"
      />
    </CardContent>
    <template v-else>
      <CardHeader class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-3">
          <HugeiconsIcon
            :icon="BotIcon"
            class="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <CardTitle class="min-w-0"
            ><h3 class="truncate" :title="agent.name">{{ agent.name }}</h3></CardTitle
          >
        </div>
        <StatusBadge :tone="stateTone"
          ><span v-if="paused && doing?.state === 'working'"
            >Finishing
            <RouterLink
              :to="ticketHref(doing.repository, doing.id)"
              class="font-mono text-sm hover:underline"
              >{{ doing.id }}</RouterLink
            >, then paused</span
          ><span v-else-if="doing?.state === 'working'"
            >Working
            <RouterLink
              :to="ticketHref(doing.repository, doing.id)"
              class="font-mono text-sm hover:underline"
              >{{ doing.id }}</RouterLink
            ></span
          ><span v-else-if="paused">Paused {{ pausedAt }}</span
          ><span v-else>{{ statusWord(state) }}</span></StatusBadge
        >
      </CardHeader>
      <CardContent class="grid min-w-0 gap-2">
        <p class="wrap-anywhere font-medium" :class="modelTone">{{ modelText }}</p>
        <p class="wrap-anywhere text-muted-foreground text-sm">
          {{ agent.runtime }} harness · {{ agent.connection || 'no connection' }}
          <StatusBadge v-if="reach" :tone="reachTone">{{ statusWord(reach) }}</StatusBadge>
        </p>
        <p class="flex flex-wrap gap-1">
          <Badge v-for="role in agent.roles" :key="role" variant="outline">{{
            STAGE_LABELS[role as Stage]
          }}</Badge>
          <span v-if="!agent.roles.length" class="text-muted-foreground text-sm">no columns</span>
        </p>
        <p class="text-muted-foreground text-sm">{{ limitsText(agent) }}</p>
        <p v-if="takesText(agent)" class="text-muted-foreground text-sm">
          {{ takesText(agent) }}
        </p>
        <AgentContextLine :agent="agent" :last="last" :now="now" />
        <p v-if="last" class="text-muted-foreground text-sm">
          Last:
          <RouterLink
            :to="ticketHref(last.repository, last.id)"
            class="font-mono text-sm hover:underline"
            >{{ last.id }}</RouterLink
          >
          {{ STAGE_LABELS[last.stage] }}, {{ last.outcome === 'running' ? 'started' : 'ended' }}
          {{ span(now - last.at) }} ago, {{ last.outcome
          }}<template v-if="last.until !== undefined"
            >, {{ resumes(last.until, now, last.refused) }}</template
          >
        </p>
        <p v-else class="text-muted-foreground text-sm">No runs yet</p>
        <p v-if="local" class="text-muted-foreground text-sm">
          Model check:
          <template v-if="testing">checking</template>
          <template v-else-if="modelCheck"
            ><span :class="modelCheck.passed ? 'text-foreground' : 'text-destructive'">{{
              modelCheck.passed ? 'passes' : 'fails'
            }}</span
            >, {{ span(now - modelCheck.at) }} ago<template v-if="modelCheck.problem"
              >, {{ modelCheck.problem }}</template
            ></template
          >
          <template v-else>not checked</template>
        </p>
        <p v-if="lacks.length" class="text-muted-foreground text-sm">
          Lacks:
          <template v-for="(gap, at) in lacks" :key="gap.guarantee"
            ><template v-if="at">, </template
            ><span :title="gap.why"
              >{{ gap.guarantee }}<span class="sr-only"> ({{ gap.why }})</span></span
            ></template
          >
        </p>
        <p v-if="later" class="text-muted-foreground text-sm">
          {{ agent.runtime }} reports tokens when its run ends
        </p>
        <AgentMeters :name="agent.name" :meters="meters" />
      </CardContent>
      <CardFooter class="mt-auto flex-wrap gap-2" data-actions>
        <Button type="button" variant="secondary" :aria-disabled="locked" @click="togglePause()">
          {{ paused ? 'Resume' : 'Pause' }} <span class="sr-only">{{ agent.name }}</span>
        </Button>
        <Button type="button" variant="ghost" :disabled="locked" @click="open()">
          Edit <span class="sr-only">{{ agent.name }}</span>
        </Button>
        <AgentCardMenu
          :name="agent.name"
          :connected="Boolean(agent.connection)"
          :local="local"
          :locked="locked"
          :checking="checking"
          @check="emit('check')"
          @test="testModel()"
          @remove="void remove()"
        />
        <FieldError v-if="error" class="basis-full">{{ error }}</FieldError>
      </CardFooter>
    </template>
  </ContentCard>
</template>
