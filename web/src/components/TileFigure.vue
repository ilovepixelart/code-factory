<script setup lang="ts">
import { cn } from '@/lib/utils'

// A tile's figure: the value, or, when there is none to show, a muted placeholder at a smaller
// size, so an empty figure never reads as a figure. The tile's footer says why it is empty.
const { value } = defineProps<{ value: string | null }>()
</script>

<template>
  <div
    data-metric-figure
    data-slot="card-title"
    :class="
      cn(
        'cn-font-heading leading-tight wrap-anywhere',
        value === null
          ? 'text-lg font-normal text-muted-foreground'
          : 'text-2xl font-semibold tabular-nums @[250px]/card:text-3xl',
      )
    "
  >
    {{ value ?? 'No data' }}
  </div>
</template>
