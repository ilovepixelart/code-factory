<script setup lang="ts">
import { ESTIMATE_NOTE, cost, count } from '../../lib/format'
import type { Dashboard } from '../../lib/factory'
import TileFigure from '../TileFigure.vue'
import { Card, CardDescription, CardFooter, CardHeader } from '@/components/ui/card'

// The factory's four figures at a glance: runs, pull requests opened, cost per PR and measurement
// spend. A count of nothing reads 0; a median of nothing has no figure, and the footer says why.
const { dashboard } = defineProps<{ dashboard: Dashboard }>()

const stateRuns = (key: string): number =>
  dashboard.runs.by_state.find((row) => row.key === key)?.runs ?? 0
const quiet = (): boolean => dashboard.prs.opened === 0
const NONE_OPENED = 'no pull requests opened in this range'
</script>

<template>
  <section
    aria-label="At a glance"
    class="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 xl:grid-cols-4"
  >
    <Card class="@container/card" size="sm" role="group" aria-label="Runs">
      <CardHeader>
        <CardDescription>Runs</CardDescription>
        <TileFigure :value="count(dashboard.runs.total)" />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>
          {{ stateRuns('finished') }} finished, {{ stateRuns('failed') }} failed,
          {{ stateRuns('stopped') }} stopped
        </p>
      </CardFooter>
    </Card>
    <Card class="@container/card" size="sm" role="group" aria-label="PRs opened">
      <CardHeader>
        <CardDescription>PRs opened</CardDescription>
        <TileFigure :value="count(dashboard.prs.opened)" />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>{{ dashboard.prs.open }} open, {{ dashboard.prs.closed }} closed unmerged</p>
      </CardFooter>
    </Card>
    <Card class="@container/card" size="sm" role="group" aria-label="Cost per PR">
      <CardHeader>
        <CardDescription>Cost per PR</CardDescription>
        <TileFigure
          :value="
            dashboard.cost.median === null
              ? null
              : cost(dashboard.cost.median, dashboard.cost.estimated)
          "
        />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p :title="dashboard.cost.estimated ? ESTIMATE_NOTE : undefined">
          {{
            quiet()
              ? NONE_OPENED
              : `median; ${String(dashboard.cost.priced)} of ${String(dashboard.cost.of)} PRs priced`
          }}
        </p>
      </CardFooter>
    </Card>
    <Card class="@container/card" size="sm" role="group" aria-label="Measurement spend">
      <CardHeader>
        <CardDescription>Measurement spend</CardDescription>
        <TileFigure
          :value="dashboard.cost.measurement == null ? null : cost(dashboard.cost.measurement)"
        />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>
          {{
            dashboard.cost.measurement == null
              ? 'No measurement costs recorded'
              : 'Recorded judge, eval and benchmark costs'
          }}
        </p>
      </CardFooter>
    </Card>
  </section>
</template>
