<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { Analytics01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import CostTables from '../components/factory/CostTables.vue'
import ExpensiveTable from '../components/factory/ExpensiveTable.vue'
import AnalyticsFrame from '../components/AnalyticsFrame.vue'
import FactoryTiles from '../components/factory/FactoryTiles.vue'
import FixRoundsTable from '../components/factory/FixRoundsTable.vue'
import MergedCostSection from '../components/factory/MergedCostSection.vue'
import RoleNotesTable from '../components/factory/RoleNotesTable.vue'
import ImprovementList from '../components/factory/ImprovementList.vue'
import RunsTable from '../components/factory/RunsTable.vue'
import ScorerGrid from '../components/factory/ScorerGrid.vue'
import { rangeQuery, shownTab } from '../lib/analytics'
import type { Dashboard } from '../lib/factory'
import { useFactoryRead } from '../lib/factoryRead'
import { span } from '../lib/format'

// What the agents' work cost and how its runs went, as the factory figures define them; how the
// work moved (merges, lead and cycle times, autonomy) is the Flow page's:
// `GET /api/factory/dashboard` for the range the address names, `7d`, `30d` or `90d`.
const EXPENSIVE_SHOWN = 5
const reads = useFactoryRead<Dashboard>('/api/factory/dashboard')
const dashboard = reads.data
const expensive = computed(() => dashboard.value?.expensive.slice(0, EXPENSIVE_SHOWN) ?? [])
const firstReview = computed(() =>
  dashboard.value?.cycle.stages.find((stage) => stage.stage === 'pr_to_review'),
)
const closedShare = computed(() => {
  const prs = dashboard.value?.prs
  if (!prs || prs.closed + prs.merged === 0) return ''
  return new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(
    prs.closed / (prs.closed + prs.merged),
  )
})
</script>

<template>
  <AnalyticsFrame
    page="/analytics/factory"
    what="the factory"
    ranged
    note="Estimates, not an invoice. Use these to pick runs to investigate, not to conclude a cause."
    :ready="dashboard !== null"
    :failed="reads.failed.value"
    :busy="reads.busy.value"
    :shown="reads.shown.value"
    @retry="void reads.refresh()"
  >
    <template v-if="dashboard">
      <FactoryTiles :dashboard="dashboard" />

      <SectionCard
        v-if="closedShare || (firstReview && firstReview.median !== null)"
        key="pr-outcomes"
        heading="pr-outcomes-heading"
        title="Pull request outcomes"
      >
        <div class="text-sm">
          <p v-if="closedShare">{{ closedShare }} of completed PRs closed unmerged</p>
          <p v-if="firstReview && firstReview.median !== null">
            Median time to first maintainer review {{ span(firstReview.median) }} across
            {{ firstReview.count }} merged PRs
          </p>
        </div>
      </SectionCard>

      <FixRoundsTable v-if="dashboard.fix_rounds?.length" :rows="dashboard.fix_rounds" />
      <RoleNotesTable v-if="dashboard.role_notes?.length" :rows="dashboard.role_notes" />

      <MergedCostSection :summary="dashboard.merged_cost" />

      <SectionCard heading="cost-heading" title="Cost per PR" :empty="!dashboard.cost.priced">
        <template #empty
          ><Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No pull request has a recorded cost in this range</EmptyTitle>
              <EmptyDescription
                >Try a wider date range to find pull requests with recorded costs.</EmptyDescription
              >
            </EmptyHeader>
          </Empty></template
        >
        <CostTables v-if="dashboard.cost.priced" :costs="dashboard.cost" />
      </SectionCard>

      <SectionCard
        heading="runs-heading"
        title="Runs"
        :count="dashboard.runs.total"
        description="Runs recorded in the board ledger"
        :empty="!dashboard.runs.total"
      >
        <template #empty
          ><Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No runs in this range</EmptyTitle>
              <EmptyDescription
                >Completed and in-progress runs appear here. Try a wider date
                range.</EmptyDescription
              >
            </EmptyHeader>
          </Empty></template
        >
        <RunsTable v-if="dashboard.runs.total" :runs="dashboard.runs" />
      </SectionCard>

      <SectionCard
        heading="expensive-heading"
        title="Most expensive pull requests"
        :count="expensive.length"
        description="The five dearest pull requests of the range"
        :empty="!expensive.length"
      >
        <template #empty
          ><Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No priced pull requests in this range</EmptyTitle>
              <EmptyDescription
                >Pull requests with recorded run costs appear here.</EmptyDescription
              >
            </EmptyHeader>
          </Empty></template
        >
        <ExpensiveTable v-if="expensive.length" :rows="expensive" />
      </SectionCard>

      <ScorerGrid
        title="Scorers"
        :scorers="dashboard.scorers"
        unavailable="Scorer results are not available yet"
        why="Scorers judge completed runs against criteria you write."
      >
        <template #action
          ><RouterLink
            :to="{ path: '/analytics/scorers', query: rangeQuery(reads.range.value) }"
            class="underline-offset-4 hover:underline text-sm"
            >All scorers</RouterLink
          ></template
        >
      </ScorerGrid>

      <!-- Shown once the evals that feed it exist: nothing here can only say it is not available. -->
      <SectionCard
        v-if="dashboard.improvements.available"
        key="improvements"
        heading="improvements-heading"
        title="Newest self-improvement PRs"
        :count="dashboard.improvements.items.length"
        :empty="dashboard.improvements.items.length === 0"
      >
        <template v-if="shownTab('/analytics/self-improvement')" #action
          ><RouterLink
            to="/analytics/self-improvement"
            class="underline-offset-4 hover:underline text-sm"
            >All self-improvement</RouterLink
          ></template
        >
        <template #empty>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No self-improvement pull requests yet</EmptyTitle>
              <EmptyDescription
                >Pull requests proposing fixes for scorer failures appear here.</EmptyDescription
              >
            </EmptyHeader>
          </Empty>
        </template>
        <ImprovementList
          v-if="dashboard.improvements.items.length"
          :items="dashboard.improvements.items"
          :now="dashboard.now"
        />
      </SectionCard>
    </template>
  </AnalyticsFrame>
</template>
