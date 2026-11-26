<script setup lang="ts">
import { computed } from 'vue'
import type { ButtonVariants } from '@/components/ui/button'
import { Button } from '@/components/ui/button'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Progress } from '@/components/ui/progress'

// AI Elements' Context over one of an agent's limits while it holds a ticket: the share used on a
// button that opens, on hover or focus, the use against the limit and its bar. The button carries
// the whole reading in its name, and its variant says how close the limit is.
const { name, label, used, max, text, tone } = defineProps<{
  /** What is measured, named for assistive tech: the agent and the limit. */
  name: string
  /** The limit's word on the button and over the bar. */
  label: string
  used: number
  max: number
  text: string
  tone: 'default' | 'warning' | 'error'
}>()

const VARIANT: Record<typeof tone, ButtonVariants['variant']> = {
  default: 'outline',
  warning: 'default',
  error: 'destructive',
}
const percent = computed(() => Math.min(100, Math.round((used / max) * 100)))
</script>

<template>
  <HoverCard :open-delay="10" :close-delay="100">
    <HoverCardTrigger as-child>
      <Button type="button" :variant="VARIANT[tone]" size="sm" :aria-label="`${name}, ${text}`">
        {{ percent }}% {{ label }}
      </Button>
    </HoverCardTrigger>
    <HoverCardContent class="flex w-64 flex-col gap-3">
      <div class="flex items-center justify-between gap-3 text-sm">
        <span class="font-medium capitalize">{{ label }}</span>
        <span class="text-muted-foreground">{{ text }}</span>
      </div>
      <Progress :model-value="percent" :aria-label="`${name} used`" />
    </HoverCardContent>
  </HoverCard>
</template>
