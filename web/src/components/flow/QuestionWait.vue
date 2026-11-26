<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Analytics01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { ask } from '../../lib/actions'
import type { RangeKey } from '../../lib/analytics'
import { span } from '../../lib/format'
import { refusalText } from '../../lib/notice'
import SectionCard from '../SectionCard.vue'

interface Wait {
  answered: number
  median_seconds: number | null
}

const props = defineProps<{ range: RangeKey }>()
const expanded = ref(false)
const { data, error, isPending } = useQuery({
  queryKey: computed(() => ['question-wait', props.range]),
  queryFn: ({ signal }) => ask<Wait>(`/api/question-wait?range=${props.range}`, signal),
  enabled: expanded,
})
</script>

<template>
  <SectionCard
    heading="question-wait-heading"
    title="Question response time"
    :empty="expanded && data?.answered === 0 && !error"
  >
    <template #empty>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>No first answers in this range</EmptyTitle>
          <EmptyDescription
            >Response time is measured from the question to its first answer.</EmptyDescription
          >
        </EmptyHeader>
      </Empty>
    </template>
    <Collapsible v-model:open="expanded">
      <CollapsibleTrigger as-child>
        <Button variant="outline" size="sm">Show response times</Button>
      </CollapsibleTrigger>
      <CollapsibleContent class="mt-3 text-sm">
        <p v-if="error" role="alert">{{ refusalText(error) }}</p>
        <p v-else-if="isPending">Reading response times…</p>
        <p v-else-if="data && data.median_seconds !== null">
          Median first response took {{ span(data.median_seconds) }} across
          {{ data.answered }} answered questions.
        </p>
      </CollapsibleContent>
    </Collapsible>
  </SectionCard>
</template>
