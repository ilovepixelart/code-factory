<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { Analytics01Icon, Wrench01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from '../components/PageNav.vue'
import AnalyticsFrame from '../components/AnalyticsFrame.vue'
import ImprovementList from '../components/factory/ImprovementList.vue'
import type { Improvements } from '../lib/factory'
import { useFactoryRead } from '../lib/factoryRead'
import { usePaged } from '../lib/paging'

// The pull requests that propose self-improvements (`GET /api/factory/improvements`), 20 to a page.
const PAGE_SIZE = 20
const reads = useFactoryRead<Improvements>(
  `/api/factory/improvements?limit=${String(PAGE_SIZE)}`,
  false,
)
const improvements = reads.data
const paged = usePaged(() => improvements.value?.items ?? null, '', PAGE_SIZE)
const now = computed(() => (improvements.value ? Math.floor(Date.now() / 1000) : 0))
</script>

<template>
  <AnalyticsFrame
    page="/analytics/self-improvement"
    what="the self-improvement pull requests"
    :ready="improvements !== null"
    :failed="reads.failed.value"
    :busy="reads.busy.value"
    @retry="void reads.refresh()"
  >
    <SectionCard
      v-if="improvements?.available"
      key="available"
      heading="improvements-heading"
      title="Pull requests"
      :count="improvements.items.length"
      :empty="improvements.items.length === 0"
    >
      <template #empty
        ><Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>No self-improvement pull requests yet</EmptyTitle>
            <EmptyDescription
              >Pull requests proposing fixes for scorer failures appear here.</EmptyDescription
            >
          </EmptyHeader>
        </Empty></template
      >
      <template v-if="!(improvements.items.length === 0)">
        <ImprovementList :items="paged.rows.value" :now="now" />
        <PageNav
          label="self-improvement pull requests"
          :fallback="PAGE_SIZE"
          :total="paged.total.value"
          :page="paged.page.value"
          :size="paged.size.value"
        />
      </template>
    </SectionCard>
    <SectionCard
      v-else-if="improvements"
      key="unavailable"
      heading="improvements-heading"
      title="Pull requests"
      empty
    >
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Wrench01Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>Self-improvement is not available yet</EmptyTitle>
            <EmptyDescription
              >Self-improvement groups scorer failures into one proposal pull
              request.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
    </SectionCard>
  </AnalyticsFrame>
</template>
