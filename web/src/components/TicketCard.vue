<script setup lang="ts">
import { sentence } from '../lib/format'
import { Badge } from '@/components/ui/badge'
import { Folder01Icon, GitBranchIcon, UnavailableIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, inject } from 'vue'
import { type Card as BoardCard, type Stage } from '../lib/board'
import { useLabelColor } from '../lib/labels'
import { chosen, keyOf } from '../lib/selection'
import { BOARD } from '../lib/live'
import { ticketHref } from '../lib/ticket'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import CardMenu from './CardMenu.vue'
import CardMenuItems from './CardMenuItems.vue'
import { CONTEXT } from './cardMenuParts'
import { useCardActions } from '../lib/cardActions'
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu'
import TicketCardBadges from './TicketCardBadges.vue'
import TicketPriority from './TicketPriority.vue'
import ColorDot from './ColorDot.vue'
import CutText from './CutText.vue'
import DeliveryStatus from './DeliveryStatus.vue'
import TicketCardMeta from './TicketCardMeta.vue'

// One board card.
const { card, stage, today } = defineProps<{ card: BoardCard; stage: Stage; today: string }>()

const TYPE_DOT: Record<string, string> = {
  feature: 'bg-primary',
  bug: 'bg-destructive',
  refactor: 'bg-foreground/40',
  upgrade: 'bg-primary',
  hotfix: 'bg-destructive',
}

const href = computed(() => ticketHref(card.repository, card.id))
const blockers = computed(() => card.links?.open_blockers ?? [])
const age = computed(() => (card.declared === stage ? card.days_in_column : null))
const selected = computed(() => chosen.has(keyOf(card.repository, card.id)))
const viewName = computed(() => `card-${card.repository}-${card.id}`.replace(/[. ]/g, '-'))
// The folder tells cards apart only beside another tracked repository (CF-1076).
const live = inject(BOARD)
const severalRepositories = computed(() => (live?.board.value?.options.repository.length ?? 0) > 1)
const footer = computed(() => severalRepositories.value || Boolean(card.branch || card.assignee))
const labelColor = useLabelColor()
const actions = useCardActions(() => card)
</script>

<template>
  <li
    class="group/card relative cursor-grab active:cursor-grabbing"
    :data-ticket="card.id"
    :data-repository="card.repository"
    :data-selected="selected ? '' : undefined"
    :style="{ viewTransitionName: viewName }"
  >
    <CardMenu :card="card" :stage="stage" :actions="actions" />
    <ContextMenu>
      <ContextMenuTrigger as="div">
        <Card
          size="sm"
          :class="
            cn(
              'data-[size=sm]:gap-2.5 data-[size=sm]:py-3 transition-shadow group-hover/card:shadow-sm group-hover/card:ring-primary/40 group-data-[selected]/card:ring-2 group-data-[selected]/card:ring-primary',
              card.blocked && 'ring-destructive/60',
              card.archived && 'opacity-60',
            )
          "
        >
          <CardContent class="grid grid-cols-1 gap-2.5" data-js-card-body>
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <span class="font-mono text-sm shrink-0 whitespace-nowrap">{{ card.id }}</span
              ><span
                v-if="card.parent"
                class="font-mono text-sm text-muted-foreground min-w-0 truncate"
                :title="`Part of ${card.parent}`"
                >↑ {{ card.parent }}</span
              >
              <span class="flex items-center gap-1.5"
                ><span
                  class="size-1.5 rounded-full"
                  :class="TYPE_DOT[card.type] ?? 'bg-foreground/40'"
                  aria-hidden="true"
                ></span
                >{{ sentence(card.type) }}</span
              >
              <TicketPriority
                v-if="card.priority"
                :priority="card.priority"
                class="ml-auto pointer-coarse:mr-8 group-hover/card:opacity-0 group-has-[[data-js-menu][data-state=open]]/card:opacity-0 group-has-[[data-js-menu]:focus-visible]/card:opacity-0"
              />
            </div>
            <p class="wrap-anywhere line-clamp-3 text-sm leading-snug font-semibold">
              <RouterLink :to="href" class="outline-none focus-visible:underline" data-js-card-link
                >{{ card.title }}<span v-if="selected" class="sr-only">, selected</span></RouterLink
              >
            </p>
            <div
              v-if="blockers.length || card.blocked"
              role="note"
              class="flex items-start gap-1.5 text-xs leading-4 text-destructive"
            >
              <HugeiconsIcon :icon="UnavailableIcon" class="size-3.5 shrink-0" aria-hidden="true" />
              <div class="min-w-0 wrap-anywhere">
                <p v-if="blockers.length">
                  Blocked by <code>{{ blockers.join(', ') }}</code>
                </p>
                <p v-if="card.blocked">Blocked: {{ card.blocked }}</p>
              </div>
            </div>
            <div v-if="card.labels.length" class="flex flex-wrap gap-1">
              <Badge v-for="label in card.labels" :key="label" variant="outline"
                ><ColorDot :color="labelColor(label)" /><CutText :text="label"
              /></Badge>
            </div>
            <TicketCardMeta :card="card" :stage="stage" :today="today" :age="age" />
            <!-- An open question is the badge below; its status line would say it twice. -->
            <DeliveryStatus v-if="!card.open_questions" :card="card" />
            <TicketCardBadges :card="card" />
          </CardContent>
          <CardFooter v-if="footer" data-card-footer class="gap-2.5 pt-1 text-muted-foreground">
            <span v-if="severalRepositories" class="flex shrink-0 items-center gap-1"
              ><HugeiconsIcon :icon="Folder01Icon" class="size-3.5 shrink-0" aria-hidden="true" />{{
                card.repository
              }}</span
            >
            <span v-if="card.branch" class="font-mono text-sm flex min-w-0 items-center gap-1"
              ><HugeiconsIcon
                :icon="GitBranchIcon"
                class="size-3.5 shrink-0"
                aria-hidden="true" /><CutText :text="card.branch"
            /></span>
            <span
              v-if="card.assignee"
              class="ml-auto grid size-5 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold uppercase text-muted-foreground ring-1 ring-border"
              :title="`@${card.assignee}`"
              >{{ [...card.assignee].slice(0, 2).join('')
              }}<span class="sr-only">@{{ card.assignee }}</span></span
            >
          </CardFooter>
        </Card>
      </ContextMenuTrigger>
      <ContextMenuContent class="w-56" :aria-label="`Actions for ${card.id}`">
        <CardMenuItems :card="card" :stage="stage" :actions="actions" :parts="CONTEXT" />
      </ContextMenuContent>
    </ContextMenu>
  </li>
</template>
