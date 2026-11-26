<script setup lang="ts">
import { Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, ref } from 'vue'
import { NOTHING_PICKED, ready, reply, type Asked, type Picking } from '../lib/questions'
import QuestionChoices from './QuestionChoices.vue'
import { Badge } from '@/components/ui/badge'
import { Button, type ButtonVariants } from '@/components/ui/button'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'

// One question, answered in place, the same wherever it is asked (the Inbox, a ticket's page): its
// topic, its text with Pick one or Pick any, and where it was asked; then its choices as cards and
// Other as the last card, one picked (the recommended one to start with) or several ticked (or
// all), sent with Answer. With no choices the answer is typed. An answered question shows its
// answer and takes a new one. The page that holds it sends what is given and says when it waits.
const {
  asked,
  waiting,
  lead = 'default',
  answer = '',
  answeredBy = '',
} = defineProps<{
  asked: Asked
  waiting?: boolean
  /** The style of the recommended choice, the page's primary when this question is next up. */
  lead?: NonNullable<ButtonVariants['variant']>
  answer?: string
  answeredBy?: string
}>()
const emit = defineEmits<{ send: [given: { choices: string[] } | { answer: string }] }>()
defineExpose({ clear })

const choices = computed(() => asked.choices)
const several = computed(() => asked.several && choices.value.length > 0)
const text = ref('')
// A pick-one question starts on its recommended choice, so taking it is one press of Answer; a
// pick-many one starts empty, as nothing says which of several are wanted.
const start = (): Picking => {
  const recommended = choices.value.find((choice) => choice.recommended)
  return several.value || recommended === undefined || answer
    ? NOTHING_PICKED
    : { choices: [recommended.text], other: null }
}
const picking = ref<Picking>(start())
const verb = computed(() => (answer ? 'Update' : 'Answer'))
const ticked = computed(() => (picking.value.other === null ? picking.value.choices.length : 0))
const sendLabel = computed(() =>
  ticked.value > 1 ? `${verb.value} with ${String(ticked.value)}` : verb.value,
)

/** Ticks every choice, the answer a list question most often gets. */
function pickAll(): void {
  picking.value = { choices: choices.value.map((choice) => choice.text), other: null }
}

/** Empties what was typed or ticked, once the page has sent it. */
function clear(): void {
  text.value = ''
  picking.value = start()
}

const sendPicked = (): void => {
  if (!waiting && ready(picking.value)) emit('send', reply(picking.value))
}
const sendTyped = (): void => {
  if (!waiting && text.value.trim() !== '') emit('send', { answer: text.value })
}
</script>

<template>
  <div class="grid grid-cols-1 gap-2" data-question>
    <p class="flex flex-wrap items-baseline gap-x-2 gap-y-1 wrap-anywhere text-sm font-medium">
      <Badge v-if="asked.topic" variant="outline" data-topic>{{ asked.topic }}</Badge>
      <span class="sr-only">&nbsp;</span>
      <span>{{ asked.text }}</span>
      <span class="sr-only">&nbsp;</span>
      <span v-if="choices.length" class="text-muted-foreground font-normal">{{
        several ? 'Pick any' : 'Pick one'
      }}</span>
    </p>
    <p v-if="asked.document" class="text-muted-foreground text-sm">Asked in {{ asked.document }}</p>
    <p v-if="answer" class="flex items-start gap-1.5 text-sm" data-answered>
      <HugeiconsIcon :icon="Tick02Icon" class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{{
        answer
      }}
      <span class="text-muted-foreground">{{
        answeredBy ? `answered via ${answeredBy}` : 'answered'
      }}</span>
    </p>
    <form v-if="choices.length" class="grid gap-2" @submit.prevent="sendPicked()">
      <QuestionChoices v-model="picking" :question="asked" @enter="sendPicked()" />
      <div class="flex items-center justify-between gap-2">
        <Button
          v-if="several"
          type="button"
          variant="ghost"
          size="sm"
          :disabled="waiting"
          @click="pickAll()"
        >
          Select all
        </Button>
        <span v-else aria-hidden="true" />
        <Button :variant="lead" type="submit" data-answer :disabled="waiting || !ready(picking)">
          {{ sendLabel }}
        </Button>
      </div>
    </form>
    <template v-else>
      <form class="max-w-xl" @submit.prevent="sendTyped()">
        <InputGroup>
          <InputGroupInput
            :model-value="text"
            name="answer"
            :aria-label="`Answer to ${asked.text}`"
            :placeholder="answer ? 'Change the answer' : 'Your answer'"
            @update:model-value="text = String($event)"
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton
              :variant="answer ? 'secondary' : lead"
              type="submit"
              :disabled="waiting || text.trim() === ''"
            >
              {{ verb }}
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </form>
    </template>
  </div>
</template>
