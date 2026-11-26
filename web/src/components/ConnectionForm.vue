<script setup lang="ts">
import { Field as VeeField, useForm } from 'vee-validate'
import { computed, onMounted, useId, useTemplateRef } from 'vue'
import type { ConnectionDraft, Kind } from '../lib/connections'
import { useReturnFocus } from '../lib/returnFocus'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

// The fields of a connection, for adding one or changing it. A key is never typed here: only the
// name of the environment variable that holds it, and only for a kind that reads one. The form's
// state and its checks are VeeValidate's, from field validation rules; the board refuses what they let through.
const props = defineProps<{
  name: string
  start: ConnectionDraft
  kinds: Kind[]
  submit: string
  error: string
  busy: boolean
}>()
const emit = defineEmits<{ save: [draft: ConnectionDraft]; cancel: [] }>()

const { handleSubmit, values } = useForm<ConnectionDraft>({
  validationSchema: {
    name: (value: unknown) =>
      (typeof value === 'string' && value.trim() !== '') || 'Give the connection a name',
  },
  initialValues: { ...props.start },
})
const nameField = useTemplateRef<InstanceType<typeof Input>>('nameField')
// A form that opens takes the keyboard to its first field, so no one loses their place.
onMounted(() => (nameField.value?.$el as HTMLInputElement | undefined)?.focus())
useReturnFocus()
const uid = useId()
const ready = computed(() => values.name.trim() !== '')
const kind = computed(() => props.kinds.find((k) => k.kind === values.kind))
const keyed = computed(() => kind.value?.key === 'required')
const login = computed(() => kind.value?.key === 'login')
const addressHint = computed(() => {
  const empty = kind.value?.base_url ? `Empty: ${kind.value.base_url}` : 'Required'
  return keyed.value || login.value ? empty : `${empty}; on this machine only`
})

const save = handleSubmit(() => {
  if (props.busy) return
  const draft = { ...values }
  emit('save', { ...draft, key_env: keyed.value ? draft.key_env : '' })
})
</script>

<template>
  <form :aria-label="name" @submit="save($event)">
    <FieldGroup class="gap-4">
      <VeeField v-slot="{ value, handleChange, errors }" name="name">
        <Field :data-invalid="errors.length ? true : undefined">
          <FieldLabel :for="`${uid}-name`">Name</FieldLabel>
          <Input
            :id="`${uid}-name`"
            ref="nameField"
            name="name"
            :model-value="value"
            class="font-mono"
            autocomplete="off"
            :aria-invalid="errors.length ? true : undefined"
            @update:model-value="handleChange($event)"
          />
          <FieldError v-if="errors.length" :errors="errors" />
        </Field>
      </VeeField>
      <FieldGroup class="grid grid-cols-1 items-start gap-4 @lg/field-group:grid-cols-2">
        <VeeField v-slot="{ value, handleChange }" name="kind">
          <Field>
            <FieldLabel :for="`${uid}-kind`">Kind</FieldLabel>
            <NativeSelect
              :id="`${uid}-kind`"
              name="kind"
              :model-value="value"
              class="w-full"
              @update:model-value="handleChange($event)"
            >
              <NativeSelectOption v-for="option in kinds" :key="option.kind" :value="option.kind">
                {{ option.label }}
              </NativeSelectOption>
            </NativeSelect>
          </Field>
        </VeeField>
        <VeeField v-slot="{ value, handleChange }" name="base_url">
          <Field>
            <FieldLabel :for="`${uid}-base_url`">Address</FieldLabel>
            <Input
              :id="`${uid}-base_url`"
              name="base_url"
              :model-value="value"
              class="font-mono"
              autocomplete="off"
              :aria-describedby="`${uid}-base_url-hint`"
              @update:model-value="handleChange($event)"
            />
            <FieldDescription :id="`${uid}-base_url-hint`">{{ addressHint }}</FieldDescription>
          </Field>
        </VeeField>
      </FieldGroup>
      <VeeField v-if="keyed" v-slot="{ value, handleChange }" keep-value name="key_env">
        <Field>
          <FieldLabel :for="`${uid}-key_env`">Key variable</FieldLabel>
          <Input
            :id="`${uid}-key_env`"
            name="key_env"
            :model-value="value"
            class="font-mono"
            autocomplete="off"
            :aria-describedby="`${uid}-key_env-hint`"
            @update:model-value="handleChange($event)"
          />
          <FieldDescription :id="`${uid}-key_env-hint`"
            >Required: the name of an environment variable set before the board starts, ending in
            _API_KEY, _AUTH_TOKEN or _TOKEN; the key goes only to this kind's own
            host</FieldDescription
          >
        </Field>
      </VeeField>
      <FieldDescription v-else-if="login" key="field-description-1">
        No key: only a codex agent takes it, on this machine's codex login, through the board
      </FieldDescription>
      <FieldDescription v-else key="field-description-2"
        >No key: a local server gets the token its docs name</FieldDescription
      >
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
