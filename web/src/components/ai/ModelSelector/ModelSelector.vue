<script setup lang="ts">
import { ArrowDown01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'

const { id, connection, models, describedby } = defineProps<{
  id: string
  connection: string
  models: string[]
  describedby: string
}>()
// AI Elements' Model Selector for an agent's model: the model menu beside the field, listing the
// models the chosen connection answered with under its name. The field stays typed, as a harness
// takes models no connection lists and an empty field means its default; an agent has no effort
// setting, so the effort menu is left out.
const model = defineModel<string>({ required: true })
</script>

<template>
  <InputGroup>
    <InputGroupInput
      :id="id"
      name="model"
      :model-value="model"
      class="font-mono"
      autocomplete="off"
      :aria-describedby="describedby"
      @update:model-value="model = String($event)"
    />
    <InputGroupAddon v-if="models.length" align="inline-end">
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <InputGroupButton type="button" size="sm" :aria-label="`Models of ${connection}`">
            Models
            <HugeiconsIcon :icon="ArrowDown01Icon" data-icon="inline-end" />
          </InputGroupButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup :model-value="model" @update:model-value="model = String($event)">
            <DropdownMenuGroup>
              <DropdownMenuLabel>{{ connection }}</DropdownMenuLabel>
              <DropdownMenuRadioItem v-for="option in models" :key="option" :value="option">
                {{ option }}
              </DropdownMenuRadioItem>
            </DropdownMenuGroup>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </InputGroupAddon>
  </InputGroup>
</template>
