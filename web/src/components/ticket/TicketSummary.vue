<script setup lang="ts">
import { computed } from 'vue'
import type { Summary } from '../../lib/ticket'

// What the ticket proved and what it did not, in one place for its reviewer (CF-400).
const { summary } = defineProps<{ summary: Summary }>()

const lines = computed(() => {
  const short = (id: string) => id.slice(0, 7)
  const treeOf = (tree: string) => (tree ? `, tree ${tree}` : '')
  const gate = summary.gate
  const held = gate?.held ? 'passed' : 'failed'
  const found = [
    gate ? `Gate ${held} on ${short(gate.commit)}${treeOf(gate.tree)}` : 'Gate not run',
  ]
  if (summary.verdict) found.push(`Review verdict: ${summary.verdict}`)
  if (summary.capture) {
    found.push(
      `Capture ${summary.capture.approved ? 'approved' : 'not approved'}, tree ${summary.capture.tree}`,
    )
  }
  return found
})
</script>

<template>
  <section aria-label="Evidence summary" class="mt-3 rounded-xl bg-muted/50 px-3 py-2.5 text-sm">
    <ul class="grid gap-1">
      <li v-for="line in lines" :key="line">{{ line }}</li>
    </ul>
    <p v-if="summary.not_proven.length === 0" class="text-muted-foreground mt-1.5">
      Not proven: nothing, every criterion names a test.
    </p>
    <template v-else>
      <p class="mt-1.5 font-medium">Not proven, checked by review only</p>
      <ul class="text-muted-foreground grid gap-0.5">
        <li v-for="criterion in summary.not_proven" :key="criterion">{{ criterion }}</li>
      </ul>
    </template>
  </section>
</template>
