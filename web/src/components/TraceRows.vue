<script setup lang="ts">
import StatusBadge from './StatusBadge.vue'
import {
  ArrowRight01Icon,
  Cancel01Icon,
  Clock01Icon,
  UnavailableIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { dur, clock, short, span, trim } from '../lib/format'
import type { Row } from '../lib/trace'
import { fromFolder } from '../lib/session_view'
import { statusWord } from '../lib/status_tone'
import CallPayloads from './CallPayloads.vue'
import { reactive } from 'vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// The rows of one turn's trace (CF-1384): the tree on the left, each call's bar on the turn's time
// axis on the right. A subagent's rows nest in one collapsible row, drawn by this same component.
const { cwd = '' } = defineProps<{ rows: Row[]; sessionId: string; cwd?: string }>()
defineOptions({ name: 'TraceRows' })
// A subagent with a failed call opens until the owner opens or closes it.
const chosen = reactive(new Map<string, boolean>())
</script>

<template>
  <template v-for="row in rows" :key="row.key">
    <li
      v-if="row.type === 'gap'"
      data-testid="gap"
      class="flex flex-wrap items-center gap-x-3 gap-y-0.5 @4xl:grid @4xl:grid-cols-[4rem_1rem_minmax(0,1fr)_6.5rem_4.5rem_8.5rem_14rem] text-muted-foreground text-sm"
    >
      <span class="hidden @4xl:block"></span>
      <HugeiconsIcon :icon="Clock01Icon" class="size-4 shrink-0" aria-hidden="true" />
      <span class="tabular-nums @4xl:col-span-5">{{ span(row.seconds) }} idle</span>
    </li>
    <li v-else-if="row.type === 'agent'">
      <Collapsible
        :data-agent="row.id"
        role="group"
        :open="chosen.get(row.id) ?? row.failed > 0"
        :unmount-on-hide="false"
        :aria-label="`Subagent ${row.name} ${short(row.id)}`"
        @update:open="chosen.set(row.id, $event)"
      >
        <CollapsibleTrigger
          class="group/trigger flex w-full items-center gap-2 py-0.5 text-start text-sm"
        >
          <HugeiconsIcon
            :icon="ArrowRight01Icon"
            class="size-4 shrink-0 transition-transform group-data-[state=open]/trigger:rotate-90"
            aria-hidden="true"
          />
          <span
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 @4xl:grid @4xl:grid-cols-[4rem_1rem_minmax(0,1fr)_6.5rem_4.5rem_8.5rem_14rem] min-w-0 flex-1"
          >
            <span class="font-mono text-sm text-muted-foreground @4xl:col-span-2">{{
              short(row.id)
            }}</span>
            <span class="flex min-w-0 items-baseline gap-2 font-medium text-foreground"
              ><span class="truncate" data-testid="agent-name">{{ row.name }}</span>
              <span class="text-muted-foreground shrink-0 text-sm font-normal"
                >{{ row.calls }} call{{ row.calls !== 1 ? 's' : '' }}</span
              ></span
            >
            <span v-if="row.failed" class="text-sm text-destructive">{{ row.failed }} failed</span>
            <span v-else class="hidden @4xl:block"></span>
            <span class="text-muted-foreground text-end text-sm tabular-nums">{{
              dur(row.total)
            }}</span>
            <span class="hidden @4xl:block"></span>
            <span
              class="relative order-last h-2.5 w-full rounded-full bg-muted @4xl:w-auto"
              aria-hidden="true"
              data-testid="agent-track"
              ><span
                data-testid="agent-bar"
                class="absolute inset-y-0 rounded-full bg-foreground/60"
                :style="{ left: `${row.bar.left}%`, width: `${row.bar.width}%` }"
              ></span
            ></span>
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ol
            :aria-label="`Entries of ${row.name} ${short(row.id)}`"
            class="ml-2 grid gap-1.5 border-l border-border pl-3"
          >
            <TraceRows :rows="row.rows" :session-id="sessionId" :cwd="cwd" />
          </ol>
        </CollapsibleContent>
      </Collapsible>
    </li>
    <li
      v-else
      class="flex flex-wrap items-center gap-x-3 gap-y-0.5 @4xl:grid @4xl:grid-cols-[4rem_1rem_minmax(0,1fr)_6.5rem_4.5rem_8.5rem_14rem] border-l-2 py-0.5 pl-2"
      :class="row.failed ? 'border-destructive bg-destructive/10' : 'border-transparent'"
    >
      <span class="font-mono text-sm text-muted-foreground w-16 shrink-0">{{
        clock(row.entry.at)
      }}</span>
      <template v-if="row.entry.kind === 'tool'">
        <HugeiconsIcon
          :icon="row.icon"
          class="size-4 text-muted-foreground shrink-0 @max-4xl:order-first"
          aria-hidden="true"
        />
        <span
          class="font-mono text-sm min-w-0 flex-1 truncate @max-4xl:order-first @max-4xl:min-w-[75%]"
          :title="row.entry.detail"
          >{{ row.entry.title }} {{ trim(fromFolder(row.entry.detail, cwd), 200) }}</span
        >
        <span class="min-w-0"
          ><StatusBadge :state="row.status"
            ><HugeiconsIcon
              v-if="row.failed"
              :icon="row.status === 'denied' ? UnavailableIcon : Cancel01Icon"
              data-icon="inline-start"
              aria-hidden="true"
            />{{ statusWord(row.status) }}</StatusBadge
          ></span
        >
        <span class="text-muted-foreground shrink-0 text-end text-sm tabular-nums">{{
          dur(row.entry.duration_seconds)
        }}</span>
        <CallPayloads
          class="order-last col-span-full basis-full"
          :session-id="sessionId"
          :seq="row.entry.seq"
        />
        <span
          class="relative order-1 h-2.5 w-full rounded-full bg-muted @4xl:col-start-7 @4xl:row-start-1 @4xl:w-auto"
          aria-hidden="true"
          data-testid="track"
          ><span
            data-testid="bar"
            class="absolute inset-y-0 rounded-full"
            :class="
              row.failed
                ? 'bg-destructive'
                : row.status === 'running'
                  ? 'bg-primary'
                  : 'bg-foreground/60'
            "
            :style="{ left: `${row.bar?.left ?? 0}%`, width: `${row.bar?.width ?? 0}%` }"
          ></span
        ></span>
      </template>
      <template v-else-if="row.entry.kind === 'prompt'">
        <span class="hidden @4xl:block"></span>
        <span class="flex min-w-0 gap-x-2 text-sm @4xl:col-span-5" :title="row.entry.detail"
          ><span class="font-semibold">Prompt</span
          ><span class="wrap-anywhere min-w-0">{{ trim(row.entry.detail, 300) }}</span></span
        >
      </template>
      <template v-else-if="row.entry.kind === 'stop'">
        <span class="hidden @4xl:block"></span>
        <span class="flex min-w-0 gap-x-2 text-sm @4xl:col-span-5"
          ><span class="text-muted-foreground">Turn ended</span
          ><span class="wrap-anywhere min-w-0">{{ trim(row.entry.detail, 240) }}</span></span
        >
      </template>
      <template v-else>
        <span class="hidden @4xl:block"></span>
        <span class="flex min-w-0 gap-x-2 text-sm @4xl:col-span-5"
          ><span class="text-muted-foreground">{{ row.entry.title }}</span
          ><span class="text-muted-foreground wrap-anywhere min-w-0">{{
            row.entry.detail
          }}</span></span
        >
      </template>
    </li>
  </template>
</template>
