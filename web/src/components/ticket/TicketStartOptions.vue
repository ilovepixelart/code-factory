<script setup lang="ts">
import { computed } from 'vue'
import { Field, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import HelpTip from '../HelpTip.vue'
import PropertyFold from './PropertyFold.vue'

// How a run starts: its permissions and whether it loops, folded under Options whose trigger names
// the choice; each control says in one line what it does.
const mode = defineModel<string>('mode', { required: true })
const loop = defineModel<boolean>('loop', { required: true })

const HELP = {
  acceptEdits: 'The agent edits files on its own and asks you before anything else.',
  bypassPermissions:
    'The agent asks nothing; the sandbox still blocks the network, secrets and writes outside the worktree.',
  loop: 'The agent starts again until the stage is done, instead of stopping after one try.',
}
const label = computed(
  () =>
    `Options: ${mode.value === 'acceptEdits' ? 'Accept edits' : 'Skip prompts'}${loop.value ? ', loop' : ''}`,
)
</script>

<template>
  <PropertyFold fold :open="false" :label="label" name="Start options" spacing="mt-2 gap-2">
    <div class="flex flex-wrap items-center gap-3">
      <ToggleGroup
        type="single"
        orientation="horizontal"
        variant="outline"
        aria-label="Permissions"
        :model-value="mode"
        @update:model-value="$event && (mode = String($event))"
      >
        <HelpTip id="agent-help-accept" :text="HELP.acceptEdits"
          ><ToggleGroupItem value="acceptEdits" aria-describedby="agent-help-accept"
            >Accept edits</ToggleGroupItem
          ></HelpTip
        >
        <HelpTip id="agent-help-skip" :text="HELP.bypassPermissions"
          ><ToggleGroupItem value="bypassPermissions" aria-describedby="agent-help-skip"
            >Skip prompts</ToggleGroupItem
          ></HelpTip
        >
      </ToggleGroup>
      <Field orientation="horizontal" class="w-auto">
        <HelpTip id="agent-help-loop" :text="HELP.loop"
          ><Switch
            id="agent-loop"
            v-model="loop"
            name="loop"
            aria-label="Loop until done"
            aria-describedby="agent-help-loop"
        /></HelpTip>
        <FieldLabel for="agent-loop">Loop</FieldLabel>
      </Field>
    </div>
  </PropertyFold>
</template>
