<script setup lang="ts">
import { computed } from 'vue'
import { thousands } from '../lib/format'
import { LARGE_PULL_LINES, pullSize, type PullCounts } from '../lib/pullSize'
import StatusBadge from './StatusBadge.vue'

// How much a pull request asks a reviewer to read: its lines added and removed, and Large past
// LARGE_PULL_LINES, where review stops catching defects well. Nothing while GitHub gave no count.
const { pull } = defineProps<{ pull: PullCounts | null | undefined }>()

const size = computed(() => pullSize(pull))
const title = computed(() =>
  size.value
    ? `${thousands(size.value.lines)} lines changed in ${String(size.value.files)} files`
    : '',
)
</script>

<template>
  <span v-if="size" class="inline-flex items-center gap-1.5" data-pull-size :title="title"
    ><span class="tabular-nums text-muted-foreground"
      >+{{ thousands(size.added) }} −{{ thousands(size.removed) }}</span
    ><StatusBadge
      v-if="size.large"
      tone="warning"
      :title="`Past ${String(LARGE_PULL_LINES)} lines a review stops catching defects well`"
      >Large</StatusBadge
    ></span
  >
</template>
