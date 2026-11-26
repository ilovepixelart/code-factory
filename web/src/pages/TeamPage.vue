<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ReadState from '../components/ReadState.vue'
import TeamGroup from '../components/team/TeamGroup.vue'
import TeamPeek from '../components/team/TeamPeek.vue'
import TeamStages from '../components/team/TeamStages.vue'
import { ask, Refused } from '../lib/actions'
import { hourMinute } from '../lib/format'
import { dialogOpen, typing } from '../lib/keys'
import { refusalText } from '../lib/notice'
import { usePaged } from '../lib/paging'
import { usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { GROUPS, GROUP_SIZE, peekKey, type TeamNow } from '../lib/teamNow'
import { Alert, AlertDescription } from '@/components/ui/alert'

// Who works on what, what waits and on whom, what needs the owner and what merged today, with
// today's stage times against the cycle's (CF-1162): `GET /api/team/now` read every 3 seconds.
// Until the first answer the page says it is reading; a read the board refused keeps the last good
// one on the page, under the server's reason. One it did not answer the header tells of.
const selected = ref('')

const {
  data: team,
  query,
  refresh,
} = usePolledRead(keys.team, (signal) => ask<TeamNow>('/api/team/now', signal), POLL.team)
const failure = computed(() => (query.error.value ? refusalText(query.error.value) : ''))
const refusal = computed(() =>
  query.error.value instanceof Refused ? query.error.value.message : '',
)
const readAt = computed(() => team.value?.now ?? 0)

const paged = GROUPS.map((g) => ({
  ...g,
  paged: usePaged(() => team.value?.groups[g.group] ?? null, g.prefix, GROUP_SIZE),
}))
const rows = computed(() =>
  team.value ? GROUPS.flatMap((g) => team.value?.groups[g.group] ?? []) : [],
)
const chosen = computed(() => rows.value.find((row) => row.key === selected.value) ?? null)

function select(key: string): void {
  selected.value = selected.value === key ? '' : key
}

// Closing the peek puts focus back on the row that opened it.
async function dismiss(): Promise<void> {
  const key = selected.value
  selected.value = ''
  await nextTick()
  document.querySelector<HTMLElement>(`[data-row="${CSS.escape(key)}"] button`)?.focus()
}

function close(event: KeyboardEvent): void {
  if (event.key === 'Escape' && selected.value && !dialogOpen() && !typing(event.target))
    void dismiss()
}

onMounted(() => {
  window.addEventListener('keydown', close)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', close)
})
</script>

<template>
  <div v-if="team" class="page-wide flex min-h-full gap-6">
    <div class="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)] content-start gap-6">
      <Alert v-if="refusal" variant="destructive">
        <AlertDescription>
          The Team page could not be read: {{ refusal
          }}<template v-if="readAt">. Showing the last read, at {{ hourMinute(readAt) }}.</template>
        </AlertDescription>
      </Alert>
      <template v-if="team">
        <TeamStages :stages="team.stages" :from="team.cycle.from" />
        <TeamGroup
          v-for="g in paged"
          :id="`team-${g.group}`"
          :key="g.group"
          :title="g.title"
          :hint="g.hint"
          :empty="g.empty"
          :next="g.next"
          :icon="g.icon"
          :paged="g.paged"
          :now="team.now"
          :selected="selected"
          :prefix="g.prefix"
          :inbox="g.inbox === true"
          @select="select($event)"
        >
          <template v-if="g.group === 'working' && (team.idle.length || team.paused.length)">
            <p
              class="flex flex-col py-2 text-sm text-muted-foreground"
              :class="{ 'px-4': team.groups.working.length }"
            >
              <span v-if="team.idle.length">Idle: {{ team.idle.join(', ') }}</span>
              <span v-if="team.paused.length">Paused: {{ team.paused.join(', ') }}</span>
            </p>
          </template>
        </TeamGroup>
      </template>
    </div>
    <TeamPeek
      v-if="team && chosen"
      :row="chosen"
      :peek="team.peek[peekKey(chosen)]"
      :now="team.now"
      @close="void dismiss()"
    />
  </div>
  <ReadState v-else shape="table" what="the team" :failed="failure" @retry="void refresh()" />
</template>
