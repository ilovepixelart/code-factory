<script setup lang="ts">
import { CheckmarkCircle02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Item, ItemContent, ItemMedia } from '@/components/ui/item'
import type { Icon } from '../lib/icon'
import ContentCard from './ContentCard.vue'

// One step of the first run: its icon until it is done, then a tick, and what the step asks.
defineProps<{ step: string; done: boolean; current: boolean; icon: Icon }>()
defineSlots<{ default?: () => unknown }>()
</script>

<template>
  <ContentCard
    role="listitem"
    :data-step="step"
    :data-done="String(done)"
    :aria-current="current ? 'step' : undefined"
  >
    <Item :variant="current ? 'muted' : 'default'" class="items-start">
      <ItemMedia variant="icon">
        <HugeiconsIcon
          :icon="done ? CheckmarkCircle02Icon : icon"
          :class="done ? 'text-success' : ''"
          aria-hidden="true"
        />
      </ItemMedia>
      <ItemContent class="min-w-0">
        <slot />
        <span v-if="done" class="sr-only">Done</span>
      </ItemContent>
    </Item>
  </ContentCard>
</template>
