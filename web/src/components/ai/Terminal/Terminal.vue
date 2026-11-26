<script setup lang="ts">
import { CommandLineIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { CodeBlock, CodeBlockContent } from '@/components/ui/code-block'
import {
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'

// AI Elements' Terminal: a command's output behind its line, closed until the reader opens it and
// kept mounted so the output stays in the page. The output is named for assistive tech.
const { title, output, label } = defineProps<{ title: string; output: string; label: string }>()
</script>

<template>
  <TraceCollapsible :unmount-on-hide="false">
    <TraceCollapsibleTrigger>
      <TraceLine>
        <TraceIcon><HugeiconsIcon :icon="CommandLineIcon" /></TraceIcon>
        <TraceTitle>{{ title }}</TraceTitle>
      </TraceLine>
    </TraceCollapsibleTrigger>
    <TraceCollapsibleContent>
      <CodeBlock size="sm">
        <CodeBlockContent wrap class="max-h-64" :aria-label="label">{{ output }}</CodeBlockContent>
      </CodeBlock>
    </TraceCollapsibleContent>
  </TraceCollapsible>
</template>
