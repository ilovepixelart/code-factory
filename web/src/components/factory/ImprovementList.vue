<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import StatusBadge from '../StatusBadge.vue'
import { span } from '../../lib/format'
import type { ImprovementItem } from '../../lib/factory'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'

// The self-improvement pull requests as rows of one surface: the number linked to GitHub, the
// title, the state and how long ago it was opened.
const { items, now } = defineProps<{ items: ImprovementItem[]; now: number }>()
</script>

<template>
  <ItemGroup class="gap-3">
    <template v-for="item in items" :key="item.url">
      <ContentCard role="listitem">
        <Item class="py-3">
          <ItemMedia class="font-mono"
            ><a :href="item.url" class="hover:underline" target="_blank" rel="noopener noreferrer"
              >#{{ item.number }}</a
            ></ItemMedia
          >
          <ItemContent class="min-w-0">
            <ItemTitle class="line-clamp-none wrap-anywhere">{{ item.title }}</ItemTitle>
          </ItemContent>
          <ItemActions>
            <StatusBadge :state="item.state" />
            <span class="text-muted-foreground tabular-nums"
              >{{ span(now - item.opened_at) }} ago</span
            >
          </ItemActions>
        </Item>
      </ContentCard>
    </template>
  </ItemGroup>
</template>
