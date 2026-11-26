<script setup lang="ts">
import SectionCard from '../../components/SectionCard.vue'
import { BotIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import PullsChart from '../../components/flow/PullsChart.vue'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import {
  CodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockHeader,
  CodeBlockTitle,
} from '@/components/ui/code-block'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from '@/components/ui/stepper'
import { STAGE_LABELS, STAGES } from '../../lib/board'
import type { ChartPoint } from '../../lib/factory'

// The display components of the /design page: Breadcrumb, Avatar, Stepper, ScrollArea, Code Block
// and the area chart, each as a screen of the board uses it.
const DAY = 86_400
const START = 1_790_000_000
const POINTS: ChartPoint[] = [3, 5, 2, 6, 4, 7, 5].map((opened, at) => ({
  start: START + at * DAY,
  opened,
  merged: Math.max(opened - 2, 0),
  label: `day ${String(at + 1)}`,
  tick: String(at + 1),
}))
const PAYLOAD = '{\n  "command": "uv run pytest",\n  "exit_code": 0\n}'
</script>

<template>
  <div class="grid gap-6">
    <SectionCard
      heading="display-heading"
      title="Display"
      description="Breadcrumb, Avatar, Stepper, ScrollArea, Code Block, Chart"
    >
      <div class="grid gap-6">
        <div class="flex flex-wrap items-center gap-6">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink as-child
                  ><RouterLink to="/tickets">Tickets</RouterLink></BreadcrumbLink
                >
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem
                ><BreadcrumbPage class="font-mono">CF-1</BreadcrumbPage></BreadcrumbItem
              >
            </BreadcrumbList>
          </Breadcrumb>
          <span class="flex items-center gap-2 text-sm"
            ><Avatar size="sm"
              ><AvatarFallback><HugeiconsIcon :icon="BotIcon" aria-hidden="true" /></AvatarFallback
            ></Avatar>
            an agent</span
          >
          <Avatar><AvatarFallback>AL</AvatarFallback></Avatar>
        </div>
        <Stepper :model-value="3" aria-label="Stage" class="w-full items-start">
          <StepperItem
            v-for="(stage, index) in STAGES"
            :key="stage"
            :step="index + 1"
            disabled
            class="relative flex w-full flex-col items-center justify-center"
          >
            <StepperTrigger>
              <StepperIndicator>{{ index + 1 }}</StepperIndicator>
            </StepperTrigger>
            <StepperSeparator
              v-if="index < STAGES.length - 1"
              class="absolute top-5 right-[calc(-50%+10px)] left-[calc(50%+20px)] block h-0.5 shrink-0 rounded-full bg-muted group-data-[state=completed]:bg-primary"
            />
            <StepperTitle>{{ STAGE_LABELS[stage] }}</StepperTitle>
          </StepperItem>
        </Stepper>
        <ScrollArea class="h-28 rounded-lg bg-muted/50">
          <ol class="grid gap-1 p-3 text-sm">
            <li v-for="n in 12" :key="n">A row of a column that scrolls, {{ n }}</li>
          </ol>
        </ScrollArea>
        <CodeBlock size="sm">
          <CodeBlockHeader>
            <CodeBlockTitle role="heading" aria-level="3">Output</CodeBlockTitle>
            <CodeBlockActions><CodeBlockCopyButton :value="PAYLOAD" /></CodeBlockActions>
          </CodeBlockHeader>
          <CodeBlockContent wrap>{{ PAYLOAD }}</CodeBlockContent>
        </CodeBlock>
      </div>
    </SectionCard>
    <!-- A Card itself: beside the samples' Card, not inside it. -->
    <PullsChart :points="POINTS" :weekly="false" />
  </div>
</template>
