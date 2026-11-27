<script setup lang="ts">
import SectionCard from '../SectionCard.vue'
import type { MergedCost } from '../../lib/factory'

const { summary } = defineProps<{ summary: MergedCost | undefined }>()
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
</script>

<template>
  <SectionCard
    v-if="summary?.merged"
    heading="merged-cost-heading"
    title="Cost per merged PR including owner time"
  >
    <div class="grid gap-1 text-sm">
      <p v-if="summary.median !== null" class="text-lg font-semibold tabular-nums">
        {{ `${summary.estimated ? 'Estimated median' : 'Median'} ${usd.format(summary.median)}` }}
      </p>
      <p class="text-muted-foreground">
        {{ summary.priced }} of {{ summary.merged }} merges have complete costs. Owner time recorded
        for {{ summary.owner_recorded }}.
      </p>
    </div>
  </SectionCard>
</template>
