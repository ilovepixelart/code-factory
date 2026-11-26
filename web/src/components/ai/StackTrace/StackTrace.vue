<script setup lang="ts">
import { CancelCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'

// AI Elements' Stack Trace: a failure as an error line that opens on the error in full (the title
// truncates) over its frames. The board's frames are a failed run's last log lines, so it opens
// with them shown and names them for assistive tech.
const { error, frames, label } = defineProps<{ error: string; frames: string[]; label: string }>()
</script>

<template>
  <Trace>
    <TraceCollapsible default-open :unmount-on-hide="false">
      <TraceCollapsibleTrigger>
        <TraceLine status="error">
          <TraceIcon><HugeiconsIcon :icon="CancelCircleIcon" /></TraceIcon>
          <TraceTitle>{{ error }}</TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
      <TraceCollapsibleContent>
        <div class="flex flex-col gap-2 rounded-md bg-muted p-3 font-mono text-xs text-foreground">
          <p class="text-destructive">{{ error }}</p>
          <ol v-if="frames.length" :aria-label="label" class="max-h-56 overflow-auto">
            <li v-for="(frame, index) in frames" :key="index" class="wrap-anywhere">
              {{ frame }}
            </li>
          </ol>
        </div>
      </TraceCollapsibleContent>
    </TraceCollapsible>
  </Trace>
</template>
