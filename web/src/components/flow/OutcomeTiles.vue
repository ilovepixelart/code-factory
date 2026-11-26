<script setup lang="ts">
import { computed } from 'vue'
import type { Flow } from '../../lib/metrics'
import { share } from '../../lib/shipped'
import TileFigure from '../TileFigure.vue'
import { Card, CardDescription, CardFooter, CardHeader } from '@/components/ui/card'

// What the range's work came to, first on the page (docs/ui.md, Flow): the share of merges that
// held first time, the share that needed a person's hand, and the share of started builds that
// merged. A row of three, as the held figures under it, so no row leaves a hole.
const { flow } = defineProps<{ flow: Flow }>()

const percent = (part: number, whole: number): string | null =>
  whole ? `${String(share(part, whole))}%` : null

const tiles = computed(() => {
  const merged = flow.merged.length
  const held = flow.merged.filter((m) => !m.reverted && m.fixes.length === 0).length
  const { assisted, autonomous, unknown } = flow.autonomy
  const classed = assisted + autonomous
  const completion = flow.completion ?? null
  return [
    {
      name: 'First-pass yield',
      value: percent(held, merged),
      note: merged
        ? `${String(held)} of ${String(merged)} merges held: not reverted, no later fix`
        : 'no merge in this range',
    },
    {
      name: 'Human intervention',
      value: percent(assisted, classed),
      note: `${String(assisted)} of ${String(classed)} merges needed a hand commit, ${String(unknown)} unknown`,
    },
    ...(completion
      ? [
          {
            name: 'Builds merged',
            value: percent(completion.merged, completion.started),
            note: `${String(completion.merged)} of ${String(completion.started)} tickets with a Build run in this range`,
          },
        ]
      : []),
  ]
})
</script>

<template>
  <section aria-label="Outcomes" class="grid grid-cols-1 gap-4 md:grid-cols-3">
    <Card
      v-for="t in tiles"
      :key="t.name"
      class="@container/card"
      size="sm"
      role="group"
      :aria-label="t.name"
    >
      <CardHeader>
        <CardDescription>{{ t.name }}</CardDescription>
        <TileFigure :value="t.value" />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>{{ t.note }}</p>
      </CardFooter>
    </Card>
  </section>
</template>
