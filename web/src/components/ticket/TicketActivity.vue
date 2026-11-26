<script setup lang="ts">
import SectionHeading from './SectionHeading.vue'
import { ref } from 'vue'
import { textParts } from '../../lib/addresses'
import { span } from '../../lib/format'
import type { ActivityEntry, TicketView } from '../../lib/ticket'
import Message from '../ai/Message/Message.vue'
import PromptInput from '../ai/PromptInput/PromptInput.vue'
import ActivityRun from './ActivityRun.vue'
import { useTicketForm } from './context'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

// What happened on the ticket, a box to comment, and while an agent runs a box to message it.
const { view, now } = defineProps<{ view: TicketView; now: number }>()

const { busy, send, press, spins } = useTicketForm()

const DOT: Record<string, string> = {
  run: 'bg-primary',
  'run.started': 'bg-primary',
  'run.ended': 'bg-primary',
  evidence: 'bg-primary',
  created: 'bg-primary',
  comment: 'bg-primary',
  message: 'bg-primary',
  answer: 'bg-primary',
}
// The owner's own turns, an answer or a message to the agent; anyone else's words start the line.
const PEOPLE = new Set(['answer', 'message'])
const comment = ref('')
const message = ref('')

async function sendComment(): Promise<void> {
  if (await send('comments', { text: comment.value })) comment.value = ''
}

// Undo is offered on the latest coordinator edit of a field while the card still holds the value
// the coordinator set; the board decides again and refuses a field that changed since.
function undoable(entry: ActivityEntry): boolean {
  const edit = entry.edit
  if (!edit) return false
  const latest = view.activity.find((a) => a.edit?.name === edit.name)
  return latest === entry && String(view.ticket[edit.name] ?? '') === edit.to
}

async function undo(entry: ActivityEntry): Promise<void> {
  await send('coordinator-undo', { name: entry.edit?.name })
}

async function sendMessage(): Promise<void> {
  if (await send('messages', { text: message.value })) message.value = ''
}
</script>

<template>
  <section aria-labelledby="activity-heading">
    <SectionHeading id="activity-heading" class="mb-3"> Activity </SectionHeading>
    <PromptInput
      v-model="comment"
      class="mb-5"
      label="New comment"
      placeholder="Comment, for people and for the next agent run"
      send="Send comment"
      :busy="busy"
      :sending="spins('comment', busy)"
      @send="press('comment', sendComment)"
    />
    <PromptInput
      v-if="view.runs.length"
      v-model="message"
      class="mb-5"
      label="Message to the running agent"
      placeholder="Message to the running agent, taken after its current tool call"
      send="Send message"
      :busy="busy"
      :sending="spins('message', busy)"
      @send="press('message', sendMessage)"
    />
    <ol
      aria-label="Activity"
      class="relative ml-2 grid grid-cols-1 gap-4 border-l border-border pl-5 text-sm wrap-anywhere"
    >
      <li v-for="(a, index) in view.activity" :key="index" class="relative">
        <span
          class="absolute top-1.5 -left-[25px] size-2 rounded-full ring-4 ring-border"
          :class="DOT[a.kind] ?? 'bg-foreground/30'"
          aria-hidden="true"
        ></span>
        <ActivityRun v-if="a.kind === 'run'" :entry="a" :now="now" />
        <div v-else class="flex items-baseline gap-3">
          <span
            ><template v-for="(part, at) in textParts(a.sentence)" :key="at"
              ><a
                v-if="part.href"
                :href="part.href"
                class="underline-offset-4 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
                >{{ part.text }}</a
              ><template v-else>{{ part.text }}</template></template
            ></span
          >
          <span class="text-muted-foreground ml-auto shrink-0 text-sm tabular-nums" data-age
            >{{ span(now - a.at) }} ago</span
          >
        </div>
        <Button
          v-if="undoable(a)"
          type="button"
          variant="ghost"
          class="mt-1"
          :disabled="busy"
          @click="press(`undo ${index}`, () => undo(a))"
          ><Spinner v-if="spins(`undo ${index}`, busy)" data-icon="inline-start" />Undo</Button
        >
        <Message v-if="a.text" class="mt-1.5" :text="a.text" :mine="PEOPLE.has(a.kind)" />
      </li>
    </ol>
  </section>
</template>
