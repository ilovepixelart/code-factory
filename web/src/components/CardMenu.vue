<script setup lang="ts">
import { MoreHorizontalIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import type { Card, Stage } from '../lib/board'
import type { CardActions } from '../lib/cardActions'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import CardMenuItems from './CardMenuItems.vue'
import { DROPDOWN } from './cardMenuParts'

// A card's menu button. `data-js-menu` on its trigger is what the board's drag and choosing code
// reads (lib/sortable.ts, lib/boardGestures.ts).
const { card, stage, actions } = defineProps<{ card: Card; stage: Stage; actions: CardActions }>()
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon-xs"
        class="absolute top-1.5 right-1.5 z-10 opacity-0 pointer-coarse:opacity-100 group-hover/card:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
        data-js-menu
        :aria-label="`Actions for ${card.id}`"
      >
        <HugeiconsIcon :icon="MoreHorizontalIcon" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-56" :aria-label="`Actions for ${card.id}`">
      <CardMenuItems :card="card" :stage="stage" :actions="actions" :parts="DROPDOWN" />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
