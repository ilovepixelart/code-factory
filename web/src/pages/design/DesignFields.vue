<script setup lang="ts">
import SectionCard from '../../components/SectionCard.vue'
import { Search01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ref } from 'vue'
import PropertyDate from '../../components/ticket/PropertyDate.vue'
import PropertyLabels from '../../components/ticket/PropertyLabels.vue'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import {
  NumberField,
  NumberFieldContent,
  NumberFieldDecrement,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/ui/number-field'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

// The form field samples of the /design page: shadcn-vue's Field family and its controls.
const fieldName = ref<string | number>('granite')
const fieldKind = ref<string>('lesson')
const fieldNote = ref<string | number>('')
const fieldLimit = ref<number | null>(3)
const fieldLoop = ref(true)
const fieldPick = ref<string>('lesson')
const fieldTicked = ref<boolean | 'indeterminate'>(true)
const fieldDue = ref('')
const fieldLabels = ref('ui, auth')
</script>

<template>
  <SectionCard
    heading="fields-heading"
    title="Fields"
    description="a label, the control, a description, a refusal under it"
  >
    <FieldGroup class="grid items-start md:grid-cols-2">
      <Field>
        <FieldLabel for="design-name">Input</FieldLabel>
        <Input id="design-name" v-model="fieldName" class="font-mono" />
        <FieldDescription>One line; font-mono for code</FieldDescription>
      </Field>
      <Field data-invalid>
        <FieldLabel for="design-refused">With a refusal</FieldLabel>
        <Input id="design-refused" model-value="0" aria-invalid="true" />
        <FieldError>A limit is a whole number above 0</FieldError>
      </Field>
      <Field>
        <FieldLabel for="design-kind">Native select</FieldLabel>
        <NativeSelect
          id="design-kind"
          :model-value="fieldKind"
          class="w-full"
          @update:model-value="fieldKind = String($event)"
        >
          <NativeSelectOption value="lesson">Lesson</NativeSelectOption>
          <NativeSelectOption value="rule">Rule</NativeSelectOption>
        </NativeSelect>
      </Field>
      <Field>
        <FieldLabel for="design-note">Textarea</FieldLabel>
        <Textarea id="design-note" v-model="fieldNote" class="font-mono" rows="3" />
      </Field>
      <Field>
        <FieldLabel for="design-limit">Number field</FieldLabel>
        <NumberField
          id="design-limit"
          :model-value="fieldLimit"
          :min="1"
          @update:model-value="fieldLimit = $event ?? null"
        >
          <NumberFieldContent>
            <NumberFieldDecrement />
            <NumberFieldInput />
            <NumberFieldIncrement />
          </NumberFieldContent>
        </NumberField>
      </Field>
      <Field>
        <FieldLabel for="design-search">Input group</FieldLabel>
        <InputGroup>
          <InputGroupInput id="design-search" type="search" placeholder="Search field" />
          <InputGroupAddon
            ><HugeiconsIcon :icon="Search01Icon" aria-hidden="true"
          /></InputGroupAddon>
        </InputGroup>
      </Field>
      <Field orientation="horizontal">
        <Switch id="design-loop" v-model="fieldLoop" />
        <FieldLabel for="design-loop">Switch</FieldLabel>
      </Field>
      <Field orientation="horizontal">
        <Checkbox id="design-tick" v-model="fieldTicked" />
        <FieldLabel for="design-tick">Checkbox</FieldLabel>
      </Field>
      <FieldSet>
        <FieldLegend variant="label">Radio group</FieldLegend>
        <RadioGroup :model-value="fieldPick" @update:model-value="fieldPick = String($event)">
          <Field orientation="horizontal">
            <RadioGroupItem id="design-lesson" value="lesson" />
            <FieldLabel for="design-lesson">Lesson</FieldLabel>
          </Field>
          <Field orientation="horizontal">
            <RadioGroupItem id="design-rule" value="rule" />
            <FieldLabel for="design-rule">Rule</FieldLabel>
          </Field>
        </RadioGroup>
      </FieldSet>
      <Field data-disabled>
        <FieldLabel for="design-disabled">Disabled input</FieldLabel>
        <Input id="design-disabled" v-model="fieldName" disabled />
      </Field>
      <PropertyDate id="design-due" v-model="fieldDue" label="Date picker" placeholder="none" />
      <PropertyLabels
        id="design-labels"
        v-model="fieldLabels"
        label="Tags input"
        placeholder="none"
      />
      <FieldError>A refusal that belongs to a row and not to one control</FieldError>
    </FieldGroup>
  </SectionCard>
</template>
