<script setup lang="ts">
import AnalyticsFrame from '../components/AnalyticsFrame.vue'
import ScorerGrid from '../components/factory/ScorerGrid.vue'
import type { ScorerCards } from '../lib/factory'
import { useFactoryRead } from '../lib/factoryRead'

// Each scorer's results in the range the address names (`GET /api/factory/scorers`), with the
// counts behind every pass rate.
const reads = useFactoryRead<ScorerCards>(
  ({ from, to }) => `/api/factory/scorers?from=${from}&to=${to}`,
)
</script>

<template>
  <AnalyticsFrame
    page="/analytics/scorers"
    what="the scorers"
    ranged
    :ready="reads.data.value !== null"
    :failed="reads.failed.value"
    :busy="reads.busy.value"
    :shown="reads.shown.value"
    @retry="void reads.refresh()"
  >
    <ScorerGrid
      v-if="reads.data.value"
      detail
      title="Results"
      description="a pass rate is yes over yes and no"
      :scorers="reads.data.value"
      unavailable="Scorers are not available yet"
      why="Scorers judge completed runs against criteria you write."
    />
  </AnalyticsFrame>
</template>
