<script setup lang="ts">
import { VisArea, VisAxis, VisLine, VisXYContainer } from '@unovis/vue'
import { Analytics01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { ChartPoint } from '../../lib/factory'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartCrosshair,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  componentToString,
  type ChartConfig,
} from '@/components/ui/chart'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

// The pull requests the board opened in each bucket of the range (delivery's records, not git's
// merges, which Shipped counts) and those of them merged, as
// ChartAreaInteractive draws two series: an area each, merged in front. The buckets are the
// factory series' (a UTC day, a week past 31 days); the chart reads to a screen reader as each
// bucket with its two counts.
const { points, weekly } = defineProps<{ points: ChartPoint[]; weekly: boolean }>()

type Data = ChartPoint

const chartConfig = {
  opened: { label: 'Opened', color: 'var(--chart-2)' },
  merged: { label: 'Merged', color: 'var(--chart-1)' },
} satisfies ChartConfig

const svgDefs = (['opened', 'merged'] as const)
  .map(
    (key) => `
  <linearGradient id="fill-${key}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="5%" stop-color="var(--color-${key})" stop-opacity="0.8" />
    <stop offset="95%" stop-color="var(--color-${key})" stop-opacity="0.1" />
  </linearGradient>`,
  )
  .join('')

// A range with no pull request would draw an empty grid.
const quiet = computed(() => points.every((p) => p.opened === 0 && p.merged === 0))
const at = (d: Data): number => d.start * 1000
const byTime = computed(() => new Map(points.map((p) => [at(p), p])))
const tick = (x: number | Date): string => byTime.value.get(Number(x))?.tick ?? ''
// A tick under at most seven buckets, the last always among them.
const ticks = computed(() => {
  const step = Math.ceil(points.length / 7)
  return points.filter((_, n) => (points.length - 1 - n) % step === 0).map(at)
})
const label = (x: number | Date): string => byTime.value.get(Number(x))?.label ?? ''
const spoken = computed(() =>
  points
    .map((p) => `${p.label}: opened ${String(p.opened)}, merged ${String(p.merged)}`)
    .join('; '),
)
const tooltip = componentToString(chartConfig, ChartTooltipContent, { labelFormatter: label })
const COLOR = [chartConfig.opened.color, chartConfig.merged.color]
</script>

<template>
  <Card class="gap-4">
    <CardHeader class="flex items-center gap-2 sm:flex-row">
      <div class="grid flex-1 gap-1">
        <CardTitle><h2 id="shipped-heading">Shipped</h2></CardTitle>
        <CardDescription>
          Pull requests the board opened per {{ weekly ? 'week' : 'day' }}, and those of them merged
        </CardDescription>
      </div>
    </CardHeader>
    <CardContent class="px-2 sm:px-6">
      <Empty v-if="quiet">
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>The board opened no pull request in this range</EmptyTitle>
          <EmptyDescription
            >Shipped counts every merge git recorded, opened by the board or not.</EmptyDescription
          >
        </EmptyHeader>
      </Empty>
      <ChartContainer
        v-else
        :config="chartConfig"
        class="aspect-auto h-64 w-full"
        :cursor="false"
        role="img"
        :aria-label="spoken"
      >
        <VisXYContainer :data="points" :svg-defs="svgDefs" :margin="{ left: -40 }">
          <VisArea :x="at" :y="(d: Data) => d.opened" color="url(#fill-opened)" :opacity="0.6" />
          <VisArea :x="at" :y="(d: Data) => d.merged" color="url(#fill-merged)" :opacity="0.6" />
          <VisLine :x="at" :y="(d: Data) => d.opened" :color="COLOR[0]" :line-width="1" />
          <VisLine :x="at" :y="(d: Data) => d.merged" :color="COLOR[1]" :line-width="1" />
          <VisAxis
            type="x"
            :x="at"
            :tick-line="false"
            :domain-line="false"
            :grid-line="false"
            :tick-values="ticks"
            :tick-format="tick"
          />
          <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" />
          <ChartTooltip />
          <ChartCrosshair :template="tooltip" :color="COLOR" />
        </VisXYContainer>
        <ChartLegendContent />
      </ChartContainer>
    </CardContent>
  </Card>
</template>
