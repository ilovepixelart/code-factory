<script setup lang="ts">
import { File01Icon, Wrench01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { ScorerCards } from '../../lib/factory'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { ItemGroup } from '@/components/ui/item'
import SectionCard from '../SectionCard.vue'
import ScorerCard from './ScorerCard.vue'

// The scorers' section: their results as a list, or why there are none: not available yet (the
// answer says so, an empty state and not an error) or available with no scorer defined.
const {
  scorers,
  title,
  description = '',
  unavailable,
  why,
  detail,
} = defineProps<{
  scorers: ScorerCards
  title: string
  description?: string
  /** What an answer that is not available yet says, as a title, and the sentence under it. */
  unavailable: string
  why: string
  detail?: boolean
}>()
defineSlots<{ action?: () => unknown }>()
const many = computed(() => new Set(scorers.cards.map((c) => c.repository)).size > 1)
</script>

<template>
  <SectionCard
    heading="scorers-heading"
    :title="title"
    :count="scorers.available ? scorers.cards.length : null"
    :description="description"
    :empty="!scorers.available || scorers.cards.length === 0"
  >
    <template v-if="$slots.action" #action><slot name="action" /></template>
    <template #empty>
      <Empty v-if="scorers.available" key="none">
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="File01Icon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>No scorers defined</EmptyTitle>
          <EmptyDescription
            >Add <code>[[scorers]]</code> to
            <code>.code-factory/config.toml</code>.</EmptyDescription
          >
        </EmptyHeader>
      </Empty>
      <Empty v-else key="unavailable">
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="Wrench01Icon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>{{ unavailable }}</EmptyTitle>
          <EmptyDescription>{{ why }}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </template>
    <ItemGroup v-if="scorers.available && scorers.cards.length" class="gap-3" aria-label="Scorers">
      <template v-for="card in scorers.cards" :key="`${card.repository}/${card.name}`">
        <ScorerCard :card="card" :detail="detail" :repository="many" />
      </template>
    </ItemGroup>
  </SectionCard>
</template>
