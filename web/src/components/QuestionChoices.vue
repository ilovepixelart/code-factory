<script setup lang="ts">
import { computed, useId } from 'vue'
import type { Asked, Picking } from '../lib/questions'
import { Checkbox } from '@/components/ui/checkbox'
import { FieldGroup, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import ChoiceCard from './ChoiceCard.vue'
import QuestionChoice from './QuestionChoice.vue'

// A question's choices as cards, a radio group for one and checkboxes for several; Other is the
// last card, its text typed in it. Every card is the same shell around its control, so one pick
// and several read alike. Other and the choices exclude each other, as the answer holds one or the
// other.
const { question } = defineProps<{ question: Asked }>()
const emit = defineEmits<{ enter: [] }>()
const picking = defineModel<Picking>({ required: true })

const name = useId()
// The radio value of Other: no choice text starts with a NUL.
const OTHER = '\u0000other'
const picked = (text: string): boolean =>
  picking.value.other === null && picking.value.choices.includes(text)
const radio = computed(() =>
  picking.value.other === null ? (picking.value.choices[0] ?? null) : OTHER,
)

function toggle(text: string): void {
  const kept = picking.value.other === null ? picking.value.choices : []
  const choices = kept.includes(text) ? kept.filter((c) => c !== text) : [...kept, text]
  picking.value = { choices, other: null }
}

function pick(value: unknown): void {
  if (value === OTHER) chooseOther(true)
  else if (typeof value === 'string') picking.value = { choices: [value], other: null }
}

function chooseOther(chosen: boolean): void {
  picking.value = { choices: [], other: chosen ? (picking.value.other ?? '') : null }
}

function typeOther(text: string | number): void {
  picking.value = { choices: [], other: String(text) }
}
</script>

<template>
  <FieldSet>
    <FieldLegend class="sr-only">Choices for {{ question.text }}</FieldLegend>
    <component
      :is="question.several ? FieldGroup : RadioGroup"
      v-bind="question.several ? {} : { name, modelValue: radio }"
      :data-slot="question.several ? 'checkbox-group' : undefined"
      class="gap-2"
      @update:model-value="question.several ? undefined : pick($event)"
    >
      <ChoiceCard v-for="(c, n) in question.choices" :key="c.text" :for="`${name}-${String(n)}`">
        <template #control>
          <Checkbox
            v-if="question.several"
            :id="`${name}-${String(n)}`"
            class="mt-0.5"
            :data-choice="String(n + 1)"
            :data-recommended="c.recommended ? '' : undefined"
            :model-value="picked(c.text)"
            @update:model-value="toggle(c.text)"
          />
          <RadioGroupItem
            v-else
            :id="`${name}-${String(n)}`"
            :value="c.text"
            class="mt-0.5"
            :data-choice="String(n + 1)"
            :data-recommended="c.recommended ? '' : undefined"
          />
        </template>
        <QuestionChoice :choice="c" />
      </ChoiceCard>
      <ChoiceCard :for="`${name}-other`">
        <template #control>
          <Checkbox
            v-if="question.several"
            :id="`${name}-other`"
            class="mt-0.5"
            :model-value="picking.other !== null"
            @update:model-value="chooseOther($event === true)"
          />
          <RadioGroupItem v-else :id="`${name}-other`" :value="OTHER" class="mt-0.5" />
        </template>
        <span class="flex min-w-0 flex-1 flex-col gap-2">
          <span class="font-medium">Other</span>
          <Input
            :model-value="picking.other ?? ''"
            :aria-label="`Other answer to ${question.text}`"
            placeholder="Type your own answer"
            @update:model-value="typeOther($event)"
            @focus="picking.other === null && chooseOther(true)"
            @keydown.enter.prevent="emit('enter')"
          />
        </span>
      </ChoiceCard>
    </component>
  </FieldSet>
</template>
