<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { post } from '../../lib/actions'
import { vRendered } from '../../lib/rendered'
import { readPayload } from '../../lib/requestPayload'
import { CodeBlock, CodeBlockContent } from '@/components/ui/code-block'

// A permission request's content as it would act (lib/requestPayload.ts). Markdown is rendered by
// the board's own renderer, as a ticket's description is; while it is not, it shows as code.
const { tool, summary } = defineProps<{ tool: string; summary: string }>()

const payload = computed(() => readPayload(tool, summary))
const html = ref('')
watch(
  payload,
  async (shown) => {
    html.value = ''
    if (shown.kind !== 'call' || !shown.markdown) return
    try {
      html.value = (
        await post<{ html: string }>('/api/agent-context/preview', { text: shown.markdown })
      ).html
    } catch {
      html.value = ''
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="grid min-w-0 gap-2">
    <CodeBlock v-if="payload.kind === 'code'" size="sm">
      <CodeBlockContent wrap class="max-h-64">{{ payload.text }}</CodeBlockContent>
    </CodeBlock>
    <template v-else>
      <dl
        v-if="payload.fields.length"
        class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm"
      >
        <template v-for="[key, value] in payload.fields" :key="key">
          <dt class="text-muted-foreground">{{ key }}</dt>
          <dd class="font-mono wrap-anywhere">{{ value }}</dd>
        </template>
      </dl>
      <CodeBlock v-if="payload.command" key="code-block-2" size="sm">
        <CodeBlockContent wrap class="max-h-64">{{ payload.command }}</CodeBlockContent>
      </CodeBlock>
      <div
        v-if="payload.markdown && html"
        v-rendered="html"
        class="typeset typeset-doc max-h-64 overflow-auto"
      ></div>
      <CodeBlock v-else-if="payload.markdown" key="code-block-3" size="sm">
        <CodeBlockContent wrap class="max-h-64">{{ payload.markdown }}</CodeBlockContent>
      </CodeBlock>
      <p v-if="payload.cut" class="text-muted-foreground text-sm">
        Cut short: the board keeps the first 300 characters of a request.
      </p>
    </template>
  </div>
</template>
