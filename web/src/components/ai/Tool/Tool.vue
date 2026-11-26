<script setup lang="ts">
import { Wrench01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { ToolCall } from '../../../generated/ToolCall'
import { thousands } from '../../../lib/format'
import { payloadText } from '../../../lib/sessions'
import {
  CodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockFooter,
  CodeBlockHeader,
  CodeBlockTitle,
} from '@/components/ui/code-block'
import { FieldError } from '@/components/ui/field'
import { Spinner } from '@/components/ui/spinner'
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'

const { name, call, error } = defineProps<{ name: string; call: ToolCall | null; error: string }>()
// AI Elements' Tool over one ledger call: a line that opens on the call's input and output. The
// call is read only once the line opens (`call` is null until then), so its content says it is
// loading or why the read failed. A closed line points at no panel, as its panel is not drawn.
const open = defineModel<boolean>('open', { required: true })
const parts = computed(() =>
  call
    ? [
        { name: 'Input', value: call.input, pending: false },
        { name: 'Output', value: call.output, pending: call.output === null },
      ].map((part) => ({ ...part, shown: payloadText(part.value) }))
    : [],
)
</script>

<template>
  <Trace>
    <TraceCollapsible v-model:open="open">
      <TraceCollapsibleTrigger
        :aria-label="name"
        v-bind="open ? {} : { 'aria-controls': undefined }"
      >
        <TraceLine>
          <TraceIcon><HugeiconsIcon :icon="Wrench01Icon" /></TraceIcon>
          <TraceTitle>Input and output</TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
      <TraceCollapsibleContent role="region" :aria-label="name" class="grid gap-3">
        <FieldError v-if="error">{{ error }}</FieldError>
        <template v-else-if="call">
          <section v-for="part in parts" :key="part.name" class="grid min-w-0 gap-1">
            <CodeBlock size="sm">
              <CodeBlockHeader>
                <CodeBlockTitle role="heading" aria-level="3">{{ part.name }}</CodeBlockTitle>
                <CodeBlockActions v-if="!part.pending">
                  <CodeBlockCopyButton :value="part.shown.text" />
                </CodeBlockActions>
              </CodeBlockHeader>
              <CodeBlockContent v-if="!part.pending" wrap class="max-h-96">{{
                part.shown.text
              }}</CodeBlockContent>
              <CodeBlockFooter v-if="part.pending">Not answered yet.</CodeBlockFooter>
              <template v-else>
                <CodeBlockFooter v-for="(n, i) in part.shown.cut" :key="i">
                  cut from {{ thousands(n) }} characters at capture
                </CodeBlockFooter>
              </template>
            </CodeBlock>
          </section>
        </template>
        <p v-else class="flex items-center gap-2 text-xs"><Spinner />Loading the call</p>
      </TraceCollapsibleContent>
    </TraceCollapsible>
  </Trace>
</template>
