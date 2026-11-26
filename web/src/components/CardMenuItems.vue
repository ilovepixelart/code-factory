<script setup lang="ts">
import { sentence } from '../lib/format'
import {
  Archive02Icon,
  ArrowRight02Icon,
  Copy01Icon,
  Delete02Icon,
  Link01Icon,
  UnfoldMoreIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { STAGE_LABELS, STAGES, type Card, type Stage } from '../lib/board'
import { PRIORITIES, type CardActions } from '../lib/cardActions'
import type { MenuParts } from './cardMenuParts'

// A card's actions as menu items, in whichever menu `parts` builds.
const { card, stage, actions, parts } = defineProps<{
  card: Card
  stage: Stage
  actions: CardActions
  parts: MenuParts
}>()
</script>

<template>
  <component :is="parts.Group">
    <component :is="parts.Sub">
      <component :is="parts.SubTrigger"
        ><HugeiconsIcon :icon="ArrowRight02Icon" aria-hidden="true" />Move to</component
      >
      <component :is="parts.SubContent">
        <component :is="parts.Group">
          <component
            :is="parts.Item"
            v-for="s in STAGES.filter((s) => s !== stage)"
            :key="s"
            :disabled="actions.busy.value"
            @select="actions.move(s)"
          >
            {{ STAGE_LABELS[s] }}
          </component>
        </component>
      </component>
    </component>
    <component :is="parts.Sub">
      <component :is="parts.SubTrigger"
        ><HugeiconsIcon :icon="UnfoldMoreIcon" aria-hidden="true" />Priority</component
      >
      <component :is="parts.SubContent">
        <component :is="parts.RadioGroup" :model-value="card.priority">
          <component
            :is="parts.RadioItem"
            v-for="p in PRIORITIES"
            :key="p"
            :value="p"
            :disabled="actions.busy.value"
            @select="actions.prioritise(p)"
          >
            {{ sentence(p || 'none') }}
          </component>
        </component>
      </component>
    </component>
    <component :is="parts.Item" @select="actions.copyLink($event)">
      <HugeiconsIcon :icon="Link01Icon" aria-hidden="true" /><span>{{
        actions.copied.value ? 'Copied' : 'Copy link'
      }}</span>
    </component>
    <component :is="parts.Item" :disabled="actions.busy.value" @select="actions.duplicate()">
      <HugeiconsIcon :icon="Copy01Icon" aria-hidden="true" />Duplicate
    </component>
    <component :is="parts.Item" :disabled="actions.busy.value" @select="actions.archive()">
      <HugeiconsIcon :icon="Archive02Icon" aria-hidden="true" />Archive
    </component>
    <component
      :is="parts.Item"
      variant="destructive"
      :disabled="actions.busy.value"
      @select="actions.remove()"
    >
      <HugeiconsIcon :icon="Delete02Icon" aria-hidden="true" />Delete
    </component>
  </component>
</template>
