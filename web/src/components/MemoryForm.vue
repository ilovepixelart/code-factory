<script setup lang="ts">
import { Field as VeeField, useForm } from 'vee-validate'
import { computed, onMounted, useId, useTemplateRef } from 'vue'
import { MEMORY_KINDS, type MemoryKind } from '../lib/memory'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

// The fields of a memory entry, for adding one or editing it. The form's state and its checks are
// VeeValidate's, from field validation rules; the board refuses what they let through.
export interface MemoryDraft {
  kind: MemoryKind
  statement: string
  why: string
  source: string
  guard: string
  /** Where it loads (CF-1166); left out, the entry keeps its own. */
  scope?: string
}

const props = defineProps<{
  name: string
  start: MemoryDraft
  submit: string
  error: string
  busy: boolean
  /** A new entry needs a source (`memory::check_new`); an edit of an existing one does not. */
  requireSource?: boolean
}>()
const emit = defineEmits<{ save: [draft: MemoryDraft]; cancel: [] }>()

const statement = useTemplateRef<InstanceType<typeof Textarea>>('statement')
// A form that opens takes the keyboard to its first field, so no one loses their place.
onMounted(() => (statement.value?.$el as HTMLTextAreaElement | undefined)?.focus())
const uid = useId()
const PLACES = [
  ['', 'Every session'],
  ['core', 'Every session, first'],
  ['spec', 'Spec runs'],
  ['build', 'Build runs'],
  ['review', 'Review runs'],
  ['paths', 'Sessions changing a path'],
] as const
const start = (props.start.scope ?? '').trim()
const known = PLACES.some(([value]) => value === start && value !== 'paths')
const written = (message: string) => (value: unknown) =>
  (typeof value === 'string' && value.trim() !== '') || message
type Values = MemoryDraft & { place: string; paths: string }
const { handleSubmit, values } = useForm<Values>({
  validationSchema: {
    statement: written('Write what the entry says'),
    source: (value: unknown) =>
      !props.requireSource || written('Name where the entry comes from')(value),
    paths: (value: unknown, { form }: { form: Record<string, unknown> }) =>
      form.place !== 'paths' || written('Name the paths it loads for')(value),
  },
  initialValues: { ...props.start, place: known ? start : 'paths', paths: known ? '' : start },
})
const ready = computed(
  () =>
    values.statement.trim() !== '' &&
    (!props.requireSource || values.source.trim() !== '') &&
    (values.place !== 'paths' || values.paths.trim() !== ''),
)

const save = handleSubmit(() => {
  const { place, paths, ...draft } = { ...values } as Values
  const scope = place === 'paths' ? paths.trim() : place
  const kept = props.start.scope === undefined && scope === ''
  emit('save', kept ? draft : { ...draft, scope })
})
</script>

<template>
  <form :aria-label="name" @submit="save($event)">
    <FieldGroup class="gap-4">
      <VeeField v-slot="{ value, handleChange }" name="kind">
        <ToggleGroup
          type="single"
          orientation="horizontal"
          variant="outline"
          aria-label="Kind"
          :model-value="value"
          @update:model-value="$event && handleChange($event)"
        >
          <ToggleGroupItem v-for="[kind, label] in MEMORY_KINDS" :key="kind" :value="kind">{{
            label
          }}</ToggleGroupItem>
        </ToggleGroup>
      </VeeField>
      <VeeField v-slot="{ value, handleChange, errors }" name="statement">
        <Field :data-invalid="errors.length ? true : undefined">
          <FieldLabel :for="`${uid}-statement`">Statement</FieldLabel>
          <Textarea
            :id="`${uid}-statement`"
            ref="statement"
            name="statement"
            :model-value="value"
            rows="2"
            :aria-invalid="errors.length ? true : undefined"
            @update:model-value="handleChange($event)"
          />
          <FieldError v-if="errors.length" :errors="errors" />
        </Field>
      </VeeField>
      <VeeField v-slot="{ value, handleChange }" name="why">
        <Field>
          <FieldLabel :for="`${uid}-why`">Why</FieldLabel>
          <Input
            :id="`${uid}-why`"
            name="why"
            :model-value="value"
            @update:model-value="handleChange($event)"
          />
        </Field>
      </VeeField>
      <VeeField v-slot="{ value, handleChange, errors }" name="source">
        <Field :data-invalid="errors.length ? true : undefined">
          <FieldLabel :for="`${uid}-source`">Source</FieldLabel>
          <Input
            :id="`${uid}-source`"
            name="source"
            :model-value="value"
            :aria-invalid="errors.length ? true : undefined"
            :aria-describedby="requireSource ? `${uid}-source-hint` : undefined"
            @update:model-value="handleChange($event)"
          />
          <FieldDescription v-if="requireSource" :id="`${uid}-source-hint`"
            >Required: where the entry comes from, such as a ticket or a file</FieldDescription
          >
          <FieldError v-if="errors.length" :errors="errors" />
        </Field>
      </VeeField>
      <VeeField v-slot="{ value, handleChange }" name="place">
        <Field>
          <FieldLabel :for="`${uid}-place`">Loads in</FieldLabel>
          <NativeSelect
            :id="`${uid}-place`"
            name="place"
            :model-value="value"
            class="w-full"
            @update:model-value="handleChange($event)"
          >
            <NativeSelectOption v-for="[where, label] in PLACES" :key="where" :value="where">{{
              label
            }}</NativeSelectOption>
          </NativeSelect>
        </Field>
      </VeeField>
      <VeeField
        v-if="values.place === 'paths'"
        v-slot="{ value, handleChange, errors }"
        keep-value
        name="paths"
      >
        <Field :data-invalid="errors.length ? true : undefined">
          <FieldLabel :for="`${uid}-paths`">Paths, comma separated</FieldLabel>
          <Input
            :id="`${uid}-paths`"
            name="paths"
            :model-value="value"
            class="font-mono"
            :aria-invalid="errors.length ? true : undefined"
            @update:model-value="handleChange($event)"
          />
          <FieldError v-if="errors.length" :errors="errors" />
        </Field>
      </VeeField>
      <VeeField
        v-if="values.kind === 'lesson'"
        key="vee-field-2"
        v-slot="{ value, handleChange }"
        keep-value
        name="guard"
      >
        <Field>
          <FieldLabel :for="`${uid}-guard`">Guard</FieldLabel>
          <Input
            :id="`${uid}-guard`"
            name="guard"
            :model-value="value"
            class="font-mono"
            @update:model-value="handleChange($event)"
          />
        </Field>
      </VeeField>
      <FieldError v-if="error">{{ error }}</FieldError>
      <Field orientation="horizontal" class="justify-end">
        <Button type="button" variant="ghost" @click="emit('cancel')">Cancel</Button>
        <Button type="submit" :disabled="!ready || busy"
          ><Spinner v-if="busy" data-icon="inline-start" />{{ submit }}</Button
        >
      </Field>
    </FieldGroup>
  </form>
</template>
