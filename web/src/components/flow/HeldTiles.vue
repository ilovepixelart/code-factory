<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { count } from '../../lib/format'
import type { Merged } from '../../lib/metrics'
import { HELD, heldList, notHeld, share } from '../../lib/shipped'
import TileFigure from '../TileFigure.vue'
import { Card, CardDescription, CardFooter, CardHeader } from '@/components/ui/card'

// Whether what shipped held (CF-1215): for each way a merge did not, how many of the range's
// merges and their share, linked to Recently merged narrowed to them. Its own row of three, so
// neither it nor the figures above leave a hole in a row.
const { merged } = defineProps<{ merged: Merged[] }>()

const route = useRoute()
const figures = computed(() =>
  HELD.map((held) => {
    const found = merged.filter((m) => notHeld(m, held.key)).length
    return {
      ...held,
      count: found,
      share: share(found, merged.length),
      to: heldList(route.query, held.key),
    }
  }),
)
</script>

<template>
  <section aria-label="Whether it held" class="grid grid-cols-1 gap-4 md:grid-cols-3">
    <Card
      v-for="f in figures"
      :key="f.key"
      class="@container/card"
      size="sm"
      role="group"
      :aria-label="f.title"
    >
      <CardHeader>
        <CardDescription>{{ f.title }}</CardDescription>
        <TileFigure :value="count(f.count)" />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>
          <template v-if="merged.length"
            >{{ f.share }}% of {{ merged.length }} merged<template v-if="f.count">
              ·
              <RouterLink :to="f.to" class="underline-offset-4 hover:underline"
                >show them</RouterLink
              ></template
            ></template
          >
          <template v-else>no merge in this range</template>
        </p>
      </CardFooter>
    </Card>
  </section>
</template>
