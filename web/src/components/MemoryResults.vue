<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import SectionCard from './SectionCard.vue'
import { Search01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from './PageNav.vue'
import type { Memory } from '../lib/memory'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'

// What a search of the docs, tickets and memory found, a page at a time (CF-368).
defineProps<{ memory: Pick<Memory, 'results' | 'matched' | 'page' | 'size'>; query: string }>()
</script>

<template>
  <SectionCard
    heading="results-heading"
    title="Search results"
    :count="memory.matched"
    :description="`for ${query}`"
    :empty="!memory.results.length"
  >
    <template #empty>
      <Empty
        ><EmptyHeader
          ><EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="Search01Icon" aria-hidden="true" /></EmptyMedia
          ><EmptyTitle>No matches</EmptyTitle
          ><EmptyDescription
            >Nothing in the docs, tickets or memory matches every word.</EmptyDescription
          ></EmptyHeader
        ></Empty
      >
    </template>
    <ItemGroup v-if="memory.results.length">
      <ContentCard
        v-for="found in memory.results"
        :key="`${found.repository}/${found.path}`"
        role="listitem"
      >
        <Item class="py-3">
          <ItemContent class="min-w-0">
            <ItemTitle class="font-mono">
              <RouterLink v-if="found.open.startsWith('/')" :to="found.open" class="hover:underline"
                >{{ found.repository }}/{{ found.path }}</RouterLink
              ><a v-else-if="found.open" :href="found.open" class="hover:underline"
                >{{ found.repository }}/{{ found.path }}</a
              ><span v-else>{{ found.repository }}/{{ found.path }}</span>
            </ItemTitle>
            <ItemDescription>{{ found.snippet }}</ItemDescription>
          </ItemContent>
        </Item>
      </ContentCard>
    </ItemGroup>
    <PageNav
      label="the search results"
      :total="memory.matched"
      :page="memory.page"
      :size="memory.size"
    />
  </SectionCard>
</template>
