<script setup lang="ts">
import { computed } from 'vue'
import type { Card } from '../lib/board'
import { span } from '../lib/format'
import { deliveryStatus, useDeliveryClock } from '../lib/delivery'
import StatusBadge from './StatusBadge.vue'

const { card, announce } = defineProps<{ card: Card; announce?: boolean }>()
const now = useDeliveryClock()
const status = computed(() => deliveryStatus(card))
const tone = computed(() => status.value?.state ?? status.value?.label.toLowerCase() ?? '')
const suffix = computed(() => {
  const current = status.value
  if (!current) return ''
  const time = now.value / 1000
  if (current.retryAt !== undefined) {
    return current.retryAt > time ? `retry in ${span(current.retryAt - time)}` : 'retry due'
  }
  return current.since === undefined ? '' : span(time - current.since)
})
</script>

<template>
  <span
    v-if="status || announce"
    class="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground"
    data-delivery-status
  >
    <!-- The live region stays one element while the status inside it comes and goes. -->
    <span :role="announce ? 'status' : undefined" class="inline-flex min-w-0">
      <!-- The label is written whole, an agent's name kept as it is named. -->
      <StatusBadge v-if="status" :state="tone">{{ status.label }}</StatusBadge>
    </span>
    <span v-if="suffix" class="tabular-nums">{{ suffix }}</span>
  </span>
</template>
