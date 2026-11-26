<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { Wrench01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import AnalyticsFrame from '../components/AnalyticsFrame.vue'

// A placeholder until the evals additions land: it reads nothing.
</script>

<template>
  <AnalyticsFrame page="/analytics/benchmarks" what="the benchmarks" ready>
    <SectionCard heading="benchmarks-heading" title="Results" empty>
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Wrench01Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>Benchmarks are not available yet</EmptyTitle>
            <EmptyDescription
              >Benchmarks compare models, runtimes and runners on the same fixed
              tasks.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
    </SectionCard>
  </AnalyticsFrame>
</template>
