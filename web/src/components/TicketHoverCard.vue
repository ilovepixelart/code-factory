<script setup lang="ts">
import { computed, inject, ref, shallowRef } from 'vue'
import { STAGE_LABELS, STAGES, type Card } from '../lib/board'
import { useLabelColor } from '../lib/labels'
import { BOARD } from '../lib/live'
import { loadTicket, ticketHref } from '../lib/ticket'
import { Badge } from '@/components/ui/badge'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Skeleton } from '@/components/ui/skeleton'
import ColorDot from './ColorDot.vue'
import CutText from './CutText.vue'
import StageGlyph from './StageGlyph.vue'

// A link to a ticket that previews it on hover and on focus: from the live board when the ticket
// is on it, else from one read of the ticket the first time the preview opens.
const { repository, ticket } = defineProps<{ repository: string; ticket: string }>()
defineOptions({ inheritAttrs: false })
defineSlots<{ default: () => unknown }>()

const live = inject(BOARD, undefined)
const read = shallowRef<Card | null>(null)
const failed = ref(false)
let asked = false

const onBoard = computed(() =>
  STAGES.flatMap((stage) => live?.board.value?.columns[stage] ?? []).find(
    (card) => card.id === ticket && card.repository === repository,
  ),
)
const preview = computed(() => onBoard.value ?? read.value)
const labelColor = useLabelColor()

async function opened(open: boolean): Promise<void> {
  if (!open || onBoard.value || asked) return
  asked = true
  try {
    read.value = (await loadTicket(repository, ticket))?.card ?? null
    failed.value = !read.value
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <HoverCard @update:open="opened($event)">
    <HoverCardTrigger as-child>
      <RouterLink :to="ticketHref(repository, ticket)" v-bind="$attrs"><slot /></RouterLink>
    </HoverCardTrigger>
    <HoverCardContent class="flex flex-col gap-2">
      <template v-if="preview">
        <span class="font-mono text-muted-foreground">{{ preview.id }}</span>
        <p class="text-sm font-medium wrap-anywhere">{{ preview.title }}</p>
        <div class="flex flex-wrap items-center gap-1">
          <Badge variant="secondary" data-preview-stage
            ><StageGlyph :stage="preview.stage" decorative />{{
              STAGE_LABELS[preview.stage]
            }}</Badge
          >
          <Badge v-if="preview.assignee" variant="outline" data-preview-assignee
            >@{{ preview.assignee }}</Badge
          >
          <Badge v-for="label in preview.labels" :key="label" variant="outline" data-preview-label
            ><ColorDot :color="labelColor(label)" /><CutText :text="label"
          /></Badge>
        </div>
      </template>
      <p v-else-if="failed" class="text-muted-foreground">{{ ticket }} could not be read</p>
      <div v-else class="flex flex-col gap-2" aria-busy="true">
        <span class="sr-only">Reading {{ ticket }}</span>
        <Skeleton class="h-3 w-16" />
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-4 w-1/2" />
      </div>
    </HoverCardContent>
  </HoverCard>
</template>
