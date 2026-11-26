<script setup lang="ts">
import SectionCard from '../../components/SectionCard.vue'
import ContentCard from '../../components/ContentCard.vue'
import { File01Icon, KanbanIcon, Tick02Icon, Wrench01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Item, ItemActions, ItemContent, ItemGroup, ItemTitle } from '@/components/ui/item'
import PageNav from '../../components/PageNav.vue'
import { FRAME, HEAD, TEXT } from '../../components/data-table/look'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

// The switches, menu, disclosure, list, table, paging and empty samples of the /design page.
const ROWS = [
  ['CF-1', 'First item', '2h'],
  ['CF-2', 'Second item', '3d'],
] as const
const mode = ref('board')
const pane = ref<string | number>('preview')
const view = ref<string | number>('one')
</script>

<template>
  <SectionCard
    heading="components-heading"
    title="Components"
    description="ToggleGroup, Tabs, DropdownMenu, Collapsible, Item, Table, Pagination, Empty"
  >
    <div class="grid gap-6">
      <div class="flex flex-wrap items-center gap-3">
        <ToggleGroup
          type="single"
          orientation="horizontal"
          variant="outline"
          aria-label="Example toggle"
          :model-value="mode"
          @update:model-value="$event && (mode = String($event))"
        >
          <ToggleGroupItem value="board">Board</ToggleGroupItem>
          <ToggleGroupItem value="list">List</ToggleGroupItem>
        </ToggleGroup>
        <Tabs v-model="view">
          <TabsList aria-label="Example tabs">
            <TabsTrigger value="one">One</TabsTrigger>
            <TabsTrigger value="two">Two</TabsTrigger>
          </TabsList>
        </Tabs>
        <nav aria-label="Example navigation">
          <Tabs model-value="all" activation-mode="manual">
            <TabsList>
              <TabsTrigger value="all" as-child>
                <RouterLink to="/design" aria-current="page">Everything</RouterLink>
              </TabsTrigger>
              <TabsTrigger value="mine" as-child>
                <RouterLink to="/design">Mine</RouterLink>
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </nav>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost">Menu</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent class="w-44" aria-label="Example menu">
            <DropdownMenuGroup>
              <DropdownMenuItem>A choice</DropdownMenuItem>
              <DropdownMenuItem variant="destructive">A destructive choice</DropdownMenuItem>
              <DropdownMenuItem disabled>A disabled choice</DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <Collapsible aria-label="Example collapsible">
          <CollapsibleTrigger as-child
            ><Button type="button" variant="ghost" size="xs"
              >A collapsible</Button
            ></CollapsibleTrigger
          >
          <CollapsibleContent class="mt-1 text-xs">What it opens.</CollapsibleContent>
        </Collapsible>
      </div>
      <Tabs v-model="pane">
        <TabsList variant="line">
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="write">Write</TabsTrigger>
        </TabsList>
        <TabsContent value="preview"
          ><p class="text-sm">Underline tabs: a ticket's content panes only.</p></TabsContent
        >
        <TabsContent value="write"><p class="text-sm">The other pane.</p></TabsContent>
      </Tabs>
      <div>
        <CardHeader class="px-0"
          ><CardTitle
            ><h3 class="flex items-center gap-2">
              A list<span class="sr-only">, </span
              ><span class="font-normal text-muted-foreground tabular-nums">2</span>
            </h3></CardTitle
          ><CardDescription>Cards in an ItemGroup</CardDescription></CardHeader
        >
        <ItemGroup class="gap-3">
          <ContentCard v-for="[id, title, age] in ROWS" :key="id" role="listitem">
            <Item size="sm">
              <ItemContent>
                <ItemTitle
                  ><span class="font-mono text-muted-foreground">{{ id }}</span
                  >{{ title }}</ItemTitle
                >
              </ItemContent>
              <ItemActions class="text-muted-foreground">{{ age }}</ItemActions>
            </Item>
          </ContentCard>
        </ItemGroup>
      </div>
      <div>
        <CardHeader class="px-0"
          ><CardTitle
            ><h3 class="flex items-center gap-2">
              A table<span class="sr-only">, </span
              ><span class="font-normal text-muted-foreground tabular-nums">1</span>
            </h3></CardTitle
          ><CardDescription>columns that compare rows</CardDescription></CardHeader
        >
        <div :class="FRAME">
          <Table :class="TEXT">
            <TableHeader :class="HEAD">
              <TableRow>
                <TableHead>Id</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Stage</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell class="font-mono text-xs text-muted-foreground">CF-1</TableCell>
                <TableCell class="font-medium">A table row</TableCell>
                <TableCell class="text-muted-foreground">Spec</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </div>
      <div>
        <CardHeader class="px-0"
          ><CardTitle><h3 class="flex items-center gap-2">Pages</h3></CardTitle
          ><CardDescription>under a list longer than one page</CardDescription></CardHeader
        >
        <PageNav label="the example list" :total="247" :page="2" :size="10" />
      </div>
      <div>
        <CardHeader class="px-0"
          ><CardTitle><h3 class="flex items-center gap-2">Empty states</h3></CardTitle
          ><CardDescription>the icon says which empty it is</CardDescription></CardHeader
        >
        <div class="grid gap-3 md:grid-cols-2">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>Nothing waits</EmptyTitle>
              <EmptyDescription>Empty means nothing is wrong: a check.</EmptyDescription>
            </EmptyHeader>
          </Empty>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="KanbanIcon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No tickets yet</EmptyTitle>
              <EmptyDescription>Only empty: the page's own icon.</EmptyDescription>
            </EmptyHeader>
          </Empty>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="File01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>No scorers defined</EmptyTitle>
              <EmptyDescription>A setting still to do: a file.</EmptyDescription>
            </EmptyHeader>
          </Empty>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Wrench01Icon" aria-hidden="true"
              /></EmptyMedia>
              <EmptyTitle>Benchmarks arrive with a later part</EmptyTitle>
              <EmptyDescription>A part not built yet: a wrench.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </div>
      </div>
    </div>
  </SectionCard>
</template>
