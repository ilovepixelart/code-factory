<script setup lang="ts">
import SectionCard from '../SectionCard.vue'
import { UserGroupIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { span } from '../../lib/format'
import { STAGE_LABELS, against, bar, noStageTimes, type StageTimes } from '../../lib/teamNow'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

// Today against this cycle (CF-1162): for each stage from filing, today's median, this cycle's,
// how far apart they are, a bar for today with a mark at the cycle's median, and the counts; one
// line while no ticket reached a stage today or this cycle (CF-1209).
const { stages, from } = defineProps<{ stages: StageTimes[]; from: string }>()
</script>

<template>
  <SectionCard
    heading="team-times"
    title="Today against this cycle"
    :description="`Median time from filing to each stage; this cycle is ${from}`"
    :empty="noStageTimes(stages)"
  >
    <template #empty
      ><Empty data-no-stage-times
        ><EmptyHeader
          ><EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="UserGroupIcon" aria-hidden="true" /></EmptyMedia
          ><EmptyTitle>No ticket reached a stage today or this cycle.</EmptyTitle>
          <EmptyDescription
            >Stage times appear here as tickets move through the workflow.</EmptyDescription
          ></EmptyHeader
        ></Empty
      ></template
    >
    <ul
      v-if="!noStageTimes(stages)"
      class="grid grid-cols-2 gap-3 md:grid-cols-4"
      aria-label="Stage times"
    >
      <li
        v-for="stage in stages"
        :key="stage.stage"
        class="grid content-start gap-1.5 rounded-xl bg-card px-4 py-3 shadow-xs"
        :data-stage="stage.stage"
      >
        <span class="text-muted-foreground text-sm">{{ STAGE_LABELS[stage.stage] }}</span>
        <span class="flex flex-wrap items-baseline gap-x-2">
          <strong
            v-if="stage.today.median === null"
            class="text-lg font-normal text-muted-foreground"
            >none today</strong
          >
          <strong v-else class="text-2xl font-semibold tabular-nums">{{
            span(stage.today.median)
          }}</strong>
          <span class="text-muted-foreground text-sm"
            ><template v-if="stage.cycle.median === null">no cycle median</template
            ><template v-else>cycle {{ span(stage.cycle.median) }}</template
            ><template v-if="against(stage.today.median, stage.cycle.median)"
              >, {{ against(stage.today.median, stage.cycle.median) }}</template
            ></span
          >
        </span>
        <span class="relative mt-0.5 h-1.5 rounded-full bg-muted" aria-hidden="true"
          ><span
            class="absolute inset-y-0 left-0 rounded-full bg-foreground/35"
            :style="{ width: `${bar(stage.today.median, stage.cycle.median).fill}%` }"
          ></span
          ><span
            v-if="stage.cycle.median !== null"
            class="absolute -inset-y-1 w-0.5 rounded-full bg-foreground"
            :style="{ left: `${bar(stage.today.median, stage.cycle.median).mark}%` }"
          ></span
        ></span>
        <span class="text-muted-foreground text-sm"
          >{{ stage.today.count }} today, {{ stage.cycle.count }} this cycle</span
        >
      </li>
    </ul>
  </SectionCard>
</template>
