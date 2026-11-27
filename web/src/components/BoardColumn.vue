<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { act } from '../lib/actions'
import {
  MERGED_SHOWN,
  STAGE_HINTS,
  STAGE_LABELS,
  newestFirst,
  type Card as BoardCard,
  type Column,
} from '../lib/board'
import { BOARD } from '../lib/live'
import { perform } from '../lib/notice'
import { vSortable, type Drop, type Sorting } from '../lib/sortable'
import ColumnMenu from './ColumnMenu.vue'
import StageGlyph from './StageGlyph.vue'
import TicketCard from './TicketCard.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

// One board column.
const { stage, cards, total, limit, collapsed, lanes, today } = defineProps<{
  stage: Column
  cards: BoardCard[]
  total: number
  limit: number | undefined
  collapsed: boolean
  lanes: [string, Record<Column, BoardCard[]>][] | null
  today: string
}>()
const emit = defineEmits<{ toggle: [] }>()

const over = computed(() => limit !== undefined && total > limit)
const hint = STAGE_HINTS[stage]
const live = inject(BOARD)

// A drop is sent as a move with the list's new order; the board stays held until the server's
// board is drawn.
async function dropped(drop: Drop | null): Promise<void> {
  if (!drop || !live) {
    live?.hold(false)
    return
  }
  const path = `/api/tickets/${encodeURIComponent(drop.repository)}/${encodeURIComponent(drop.id)}`
  await perform(
    () => act('POST', `${path}/move`, { stage: drop.stage, order: drop.order }),
    () => live.refresh({ force: true, beforeApply: drop.undo }),
  )
  live.hold(false)
}
const sorting = (group: string): Sorting => ({
  group,
  start: () => live?.hold(true),
  drop: (drop) => void dropped(drop),
})
// Merged keeps its newest few until asked for the rest: the board is for work in flight (CF-1077).
const everything = ref(false)
const ordered = computed(() => (stage === 'merged' ? newestFirst(cards) : cards))
const listed = computed(() =>
  stage === 'merged' && !everything.value ? ordered.value.slice(0, MERGED_SHOWN) : ordered.value,
)
const rest = computed(() =>
  stage === 'merged' ? Math.max(0, ordered.value.length - MERGED_SHOWN) : 0,
)
// The column is a muted region, not a Card: the tickets in it are the board's Cards.
</script>

<template>
  <section
    :id="`stage-${stage}`"
    size="sm"
    :aria-labelledby="`column-${stage}`"
    :data-js-column="stage"
    :data-count="cards.length"
    :data-collapsed="collapsed ? '' : undefined"
    :data-over-limit="over ? '' : undefined"
    :aria-description="over ? 'over its work-in-progress limit' : undefined"
    class="group/column relative flex max-h-full min-w-64 flex-1 basis-0 flex-col gap-1.5 rounded-xl border pt-2.5 pb-2 text-sm data-[collapsed]:w-11 data-[collapsed]:min-w-11 data-[collapsed]:flex-none"
  >
    <div class="px-3 pb-2 group-data-[collapsed]/column:px-0">
      <div class="text-sm font-medium">
        <h2
          :title="`${hint}. Click to fold or open.`"
          class="flex items-center gap-2 group-data-[collapsed]/column:flex-col group-data-[collapsed]/column:gap-2.5"
        >
          <StageGlyph :stage="stage" decorative />
          <button
            :id="`column-${stage}`"
            type="button"
            class="cursor-pointer font-semibold hover:text-primary group-data-[collapsed]/column:[writing-mode:vertical-rl] group-data-[collapsed]/column:after:absolute group-data-[collapsed]/column:after:inset-0"
            :aria-expanded="!collapsed"
            :title="`${hint}. Click to fold.`"
            @click="emit('toggle')"
          >
            {{ STAGE_LABELS[stage] }}
          </button>
          <span
            v-if="limit === undefined"
            data-lane-count-pill
            class="text-muted-foreground tabular-nums"
            >{{ cards.length }}</span
          >
          <span
            v-else
            data-lane-count-pill
            class="tabular-nums"
            :class="over ? 'font-semibold text-destructive' : 'text-muted-foreground'"
            title="Cards in this column against its work-in-progress limit"
            >{{ total }}/{{ limit }}</span
          >
          <span
            class="text-muted-foreground ml-auto min-w-0 truncate text-sm font-normal group-data-[collapsed]/column:hidden"
            >{{ hint }}</span
          >
          <ColumnMenu :stage="stage" :limit="limit" />
        </h2>
      </div>
    </div>
    <div class="min-h-0 flex-1 px-1 group-data-[collapsed]/column:hidden">
      <ScrollArea class="h-full">
        <div v-if="lanes" class="grid min-h-20 content-start gap-3 p-1 pb-2">
          <section
            v-for="([name, cells], index) in lanes"
            :key="name"
            :data-lane="name"
            :data-lane-count="cells[stage].length"
            class="grid min-w-0 gap-1.5"
            :aria-label="name"
          >
            <h3 class="flex items-center gap-1.5 px-1 text-sm font-medium text-muted-foreground">
              {{ name }}<span class="tabular-nums">{{ cells[stage].length }}</span>
            </h3>
            <ul
              v-sortable="sorting(`lane-${index}`)"
              :aria-label="`${name}, ${STAGE_LABELS[stage]} tickets`"
              :data-stage="stage"
              class="grid min-h-10 min-w-0 content-start gap-2 rounded-md"
            >
              <TicketCard
                v-for="card in cells[stage]"
                :key="`${card.repository}/${card.id}`"
                :card="card"
                :stage="stage"
                :today="today"
              />
            </ul>
          </section>
        </div>
        <ul
          v-else
          v-sortable="sorting('tickets')"
          :aria-label="`${STAGE_LABELS[stage]} tickets`"
          :data-stage="stage"
          class="grid min-h-20 content-start gap-2 p-1 pb-2"
        >
          <TicketCard
            v-for="card in listed"
            :key="`${card.repository}/${card.id}`"
            :card="card"
            :stage="stage"
            :today="today"
          />
          <li v-if="rest > 0 || everything" class="flex justify-center pt-1">
            <Button type="button" variant="ghost" @click="everything = !everything">
              {{ everything ? 'Show fewer' : `Show ${rest} more` }}
            </Button>
          </li>
        </ul>
      </ScrollArea>
    </div>
  </section>
</template>
