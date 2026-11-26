<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { MoreHorizontalIcon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'
import { STAGE_DOT, STAGE_LABELS, STAGES } from '../lib/board'
import { LABEL_COLORS } from '../lib/format'
import DesignComponents from './design/DesignComponents.vue'
import DesignDisplay from './design/DesignDisplay.vue'
import DesignFields from './design/DesignFields.vue'
import DesignOverlays from './design/DesignOverlays.vue'
import DesignStates from './design/DesignStates.vue'

// The board's showcase of the shadcn-vue components it uses, as they render here in this theme;
// the rules are in docs/design.md.
const TOKENS = [
  ['background', 'bg-background'],
  ['foreground', 'bg-foreground'],
  ['card', 'bg-card'],
  ['muted', 'bg-muted'],
  ['muted-foreground', 'bg-muted-foreground'],
  ['primary', 'bg-primary'],
  ['sidebar', 'bg-sidebar'],
  ['sidebar-accent', 'bg-sidebar-accent'],
  ['secondary', 'bg-secondary'],
  ['accent', 'bg-accent'],
  ['destructive', 'bg-destructive'],
  ['border', 'bg-border'],
] as const
const VARIANTS = ['default', 'secondary', 'outline', 'ghost', 'destructive', 'link'] as const
const SIZES = ['xs', 'sm', 'default', 'lg'] as const
</script>

<template>
  <div class="page-wide grid grid-cols-1 gap-6">
    <p class="text-sm text-muted-foreground">
      The shadcn-vue components the board uses, as they render here: style reka-vega, the zinc base
      with the indigo theme, hugeicons. The rules are in docs/design.md.
    </p>

    <SectionCard
      heading="theme-heading"
      title="Theme"
      description="the theme's own tokens; each follows dark mode"
    >
      <div class="grid gap-4 text-sm">
        <div class="flex flex-wrap gap-3">
          <span v-for="[token, fill] in TOKENS" :key="token" class="flex items-center gap-2"
            ><span
              :data-testid="`swatch-${token}`"
              class="size-6 rounded-md border"
              :class="fill"
            ></span
            >{{ token }}</span
          >
        </div>
        <div class="flex flex-wrap gap-3">
          <span v-for="stage in STAGES" :key="stage" class="flex items-center gap-2"
            ><span
              :data-testid="`swatch-stage-${stage}`"
              class="size-6 rounded-md"
              :class="STAGE_DOT[stage]"
            ></span
            >{{ STAGE_LABELS[stage] }}</span
          >
        </div>
        <div class="flex flex-wrap gap-3">
          <span v-for="(fill, at) in LABEL_COLORS" :key="fill" class="flex items-center gap-2"
            ><span class="size-2 rounded-full" :class="fill"></span>label {{ at + 1 }}</span
          >
        </div>
      </div>
    </SectionCard>

    <SectionCard
      heading="buttons-heading"
      title="Button"
      description="one default (primary) Button per screen"
    >
      <div class="grid gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <Button v-for="variant in VARIANTS" :key="variant" type="button" :variant="variant">{{
            variant
          }}</Button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            v-for="size in SIZES"
            :key="size"
            type="button"
            variant="secondary"
            :size="size"
            >{{ size }}</Button
          >
          <Button type="button" variant="outline"
            ><HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />With
            an icon</Button
          >
          <Button type="button" variant="ghost" size="icon" aria-label="Icon button"
            ><HugeiconsIcon :icon="MoreHorizontalIcon" aria-hidden="true"
          /></Button>
          <Button as-child variant="outline"><a href="/design">A link</a></Button>
        </div>
        <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Disabled buttons">
          <Button
            v-for="variant in VARIANTS"
            :key="variant"
            type="button"
            :variant="variant"
            disabled
            >{{ variant }}</Button
          >
        </div>
        <ButtonGroup aria-label="A button group">
          <ButtonGroupText>2 selected</ButtonGroupText>
          <Button type="button" variant="outline">Move</Button>
          <Button type="button" variant="outline">Archive</Button>
        </ButtonGroup>
      </div>
    </SectionCard>

    <DesignStates />
    <DesignComponents />
    <DesignDisplay />
    <DesignOverlays />
    <DesignFields />
  </div>
</template>
