<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import { statementOf, type MemoryRecord, type RetiredRecord } from '../lib/memory'
import { ref } from 'vue'
import SectionCard from './SectionCard.vue'
import { Button } from '@/components/ui/button'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// The retired entries, closed until opened and absent while there are none (CF-1195); a merge
// names the statement it went into, a retired one included (CF-1171-R6).
const { retired, active } = defineProps<{ retired: RetiredRecord[]; active: MemoryRecord[] }>()
const open = ref(false)
const keyOf = (r: { repository: string; id: string }): string => `${r.repository}/${r.id}`
const mergedInto = (repository: string, id: string): string =>
  statementOf(repository, id, [...active, ...retired])
</script>

<template>
  <Collapsible v-if="retired.length" v-model:open="open" as-child :unmount-on-hide="false">
    <SectionCard
      heading="memory-history"
      title="History"
      :count="retired.length"
      description="Retired and merged entries."
    >
      <template #action>
        <CollapsibleTrigger as-child>
          <Button type="button" variant="ghost" size="sm">{{ open ? 'Hide' : 'Show' }}</Button>
        </CollapsibleTrigger>
      </template>
      <CollapsibleContent>
        <ItemGroup>
          <ContentCard
            v-for="gone in retired"
            :key="keyOf(gone)"
            role="listitem"
            :aria-label="gone.statement"
          >
            <Item class="py-3">
              <ItemContent>
                <ItemTitle class="wrap-anywhere">{{ gone.statement }}</ItemTitle>
                <ItemDescription class="flex flex-wrap items-center gap-x-2"
                  ><Badge variant="outline">{{ gone.merged_into ? 'merged' : 'retired' }}</Badge
                  ><span v-if="gone.merged_into"
                    >into "{{ mergedInto(gone.repository, gone.merged_into) }}"</span
                  ><span v-else>{{ gone.retired }}</span
                  ><span>{{ gone.repository }}</span></ItemDescription
                >
              </ItemContent>
            </Item>
          </ContentCard>
        </ItemGroup>
      </CollapsibleContent>
    </SectionCard>
  </Collapsible>
</template>
