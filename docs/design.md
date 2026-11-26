# Design language

The web app is shadcn-vue and nothing else: style `reka-vega` on the `zinc` base colour with the
`indigo` theme, hugeicons, Inter (`web/components.json`). shadcn-vue's documentation decides how a screen is built;
this page names the choices made inside it, the rules the guard tests hold, and the few parts that
are the board's own. The `/design` page (`web/src/pages/DesignPage.vue`) shows every component the
board uses as it renders here, in both themes.

## Where the rules are

| Topic | shadcn-vue's documentation |
|---|---|
| A component's use, parts and props | shadcn-vue.com/docs/components/<name>, and the source the CLI wrote in `web/src/components/ui` |
| The rules an agent follows | its agent skill: `SKILL.md` (Critical Rules) and `rules/styling.md`, `rules/forms.md`, `rules/composition.md`, `rules/icons.md` |
| Theme and dark mode | shadcn-vue.com/docs/theming, shadcn-vue.com/docs/dark-mode/vite |
| Forms | shadcn-vue.com/docs/forms/vee-validate (VeeValidate field rules) |
| Screens | shadcn-vue.com/blocks, shadcn-vue.com/charts/area |
| Rendered Markdown | shadcn-vue.com/docs/typeset |

A component is added only with the CLI, from `web/`:
`pnpm dlx shadcn-vue@2.9.0 add <name>`. Its files stay as the CLI wrote them; the one change allowed
is the narrowest cast a file needs to type-check under `exactOptionalPropertyTypes`, named in its
commit.

## The rules the tests hold

Each rule is shadcn-vue's; the test fails for a new breach, and its own cases prove it flags the
breach and passes the correct form.

| Rule | Test |
|---|---|
| Colours are the theme's semantic tokens (`bg-primary`, `text-muted-foreground`, `border-border`); no palette colour, no `white` or `black`, no arbitrary colour, no `dark:` override | `web/src/design.test.ts` |
| `class` on a component that has variants (`Button`, `Badge`, `Alert`, `Card`, `Item`, `Toggle`, `ToggleGroupItem`, `Empty`, `Kbd`) is for layout only: its colour and type come from its variant and size | `web/src/design.test.ts` |
| No daisyUI class and none of the board's old tokens (`btn`, `badge-*`, `menu`, `pill`, `surface`, `base-200`, `stage-*`, `label-*`, `tone-*`, ...) | `web/src/design.test.ts` |
| `gap-*`, never `space-x-*` or `space-y-*` | `web/src/design.test.ts` |
| Icons are `HugeiconsIcon` with an icon object from `@hugeicons/core-free-icons`; inside a shadcn-vue component an icon takes no size class (the component sizes it) | `web/src/design.test.ts` |
| A titled `Empty` shows its icon in `EmptyMedia variant="icon"` | `web/src/design.test.ts` |
| An `EmptyTitle` is a short title (no colon, one sentence, at most 50 characters); the sentence goes in `EmptyDescription` | `web/src/design.test.ts` |
| One surface level: no `Card`, bordered box or component that draws one inside a `Card`, a `Sheet`'s or a `Dialog`'s content | `web/src/design.test.ts` |
| A section is a `SectionCard`, a list section shows its count, an `Empty` sits in its section's `empty` slot | `web/src/anatomy.test.ts` |
| A list of `Item`s uses default Items in an `ItemGroup`. Records with their own details or actions use `ContentCard` surfaces with a gap between records. The configured agents use two cards per row from `md` | `web/src/design.test.ts` |
| A button is `Button` (a sidebar entry `SidebarMenuButton`); an icon-only `Button` carries `aria-label`; a `Button` that does not submit says `type="button"` (one inside a `*Trigger as-child` takes the trigger's) | `web/src/buttons.test.ts` |
| A control is `Input`, `Textarea`, `NativeSelect`, `Checkbox`, `Switch`, `RadioGroup`, ... inside the Field family; an error under it is `FieldError` | `web/src/fields.test.ts` |
| A status word is `StatusBadge` (`web/src/components/StatusBadge.vue`), never a `Badge` given a status variant; its words open with a capital. Loading is `Spinner`, a callout is `Alert`, an empty state is `Empty` | `web/src/states.test.ts` |
| A card's or a ticket's status words start with a capital (`Checks passed`, `Blocked by CF-2`, a pull request's `Open`), as its delivery status does; a label, a type or a priority keeps the case it was written in | `web/src/components/TicketCard.words.test.ts` |
| A menu is `DropdownMenu` (or `Popover` for a form), a switch between views `Tabs` or `ToggleGroup`, a disclosure `Collapsible`, a table `Table`, and a data table the shared `DataTable` (`web/src/components/data-table/`, shadcn-vue's Data Table on TanStack Table v9: sort, filter and page in the address, a Columns menu, row selection); `Table` directly only for the short fixed lists the test names | `web/src/structures.test.ts` |
| Tables share a rounded card surface at `text-sm`, a muted header and divider-free rows (`web/src/components/data-table/look.ts`). The toolbar sits above the table when it has a filter, a Columns menu or mobile sorting (filter left, Columns and Sort right), a footer under it only when rows can be chosen ("n of m row(s) selected.") or there is a second page (the range, Previous and Next as outline buttons); amounts right-aligned in medium weight, other figures right-aligned; every header that sorts shows a faint up-down mark until it is the sort; an sr-only caption names each table | `web/src/components/data-table/DataTable.test.ts` |
| Filtering: a page whose table is the page (Tickets List, Archive) filters from the header's search box; a table inside a section filters from its own box only when it can run past one page (Flow's Recently merged and Stuck), and then says "No ... matches" in the table and counts "n of m" in its section. Paging: a table pages when its rows can grow without bound; a fixed top N says so instead (Most expensive pull requests). The Columns menu only where a table has more columns than a person reads at once (the Tickets List, kept per browser; Recently merged). Below 768 px the Tickets List, Archive and wide Factory tables show rows as separate cards. Factory cards label their fields and offer a sort menu. Other tables scroll sideways within their surface, with the far edge faded | `web/src/components/data-table/DataTable.test.ts`, `web/src/components/TicketList.test.ts`, `web/src/pages/FlowPage.test.ts` |

A guard with an allowlist names a reason per file and fails for a listed file that no longer
offends (`web/src/test/guard.ts`), so a list only shrinks.

The rest of the critical rules hold in review: `size-*` when width and height are equal,
`truncate`, `cn()` for conditional classes, Items inside an `ItemGroup`, menu items inside their
group, a `Dialog` or `Sheet` always has its `Title` (`sr-only` when the page names it otherwise),
the full `Card` composition (`CardHeader`, `CardTitle`, `CardDescription`, `CardAction`,
`CardContent`, `CardFooter`), `Separator` for a rule, `Skeleton` for a placeholder, vue-sonner for
toasts (`web/src/lib/noticeToasts.ts`; a bar fixed to the bottom edge carries `data-holds-bottom`
so the toasts sit above it), `data-icon="inline-start"` or `"inline-end"` on an icon
beside a `Button`'s words. A form is `FieldGroup` of `Field`s, a refusal a `FieldError` with
`data-invalid` on its `Field` and `aria-invalid` on the control; a form that checks its values
before it sends them keeps them in VeeValidate field rules (`AgentForm`, `ConnectionForm`,
`MemoryForm`, `NewTicket`).

## Page anatomy

Every page is built in one order; `web/src/anatomy.test.ts` and `web/src/design.test.ts` hold it.

| Part | How it is built |
|---|---|
| Header | The page title on the left; the page's actions on the right, the primary action last (`#header-controls` in `web/src/App.vue`) |
| Toolbar | Filters and the range, under the header, only when there is something to filter |
| Section | `SectionCard` (`web/src/components/SectionCard.vue`), flat on the inset page panel, no `Card` around it: a heading row of the title, the count when the section is a list and the section's action, then its content. Space separates adjacent sections. A description is no line of its own: an info mark beside the title shows it on hover (`title`), and it is the section's `aria-describedby`, so it adds no tab stop. A heading is the title and count; anything else earns its place or goes one hover or click away. A file draws a `Card` only for a surface that is not a section (metric tiles, the agent cards, a ticket on the board), listed with its reason in `web/src/anatomy.test.ts` |
| Content | Record lists use full-width card surfaces with space between them. Tables share column headers for comparing records. Each row is laid out by `Item`'s own parts and never a `grid` or `flex` of its own (`a_row_is_laid_out_by_its_Item_parts`): `ItemHeader` for its context line (a ticket and an age), `ItemContent` with `ItemTitle` and `ItemDescription`, `ItemActions` with one emphasised action (`secondary`, or the page's first `default`) and the rest `ghost`, `ItemFooter` for an error; a table is `Table`. One surface level: no `Card`, no bordered box and no component that draws one inside a `Card` or a `Sheet`'s or `Dialog`'s content, except the table's own surface |
| Empty | The section's `Empty` in `SectionCard`'s `empty` slot uses a card below the toolbar. Its icon, title and description share the card's horizontal center. |
| Loading | `ReadState` until the first answer (its call sites and props stay as they are) |
| Errors | An `Alert` in the section that failed, with Read again |
| Forms | The `Field` family. Labels sit above their controls. Related fields use a Tailwind container-query grid that stacks when the form gets narrow. Checkboxes and switches keep their labels inline. In a `Sheet`, the body scrolls and the footer puts Cancel before the primary submit. |

## Theme

The theme is shadcn-vue's preset, written by its CLI into `web/src/styles/app.css` and
`web/src/components/ui`: style `vega` (the standard size: 14 px rows, buttons and inputs, 12 px
badges), base colour `zinc` (cool grey neutrals), theme `indigo`, radius `small`, font Inter,
hugeicons (preset code `aAxkum`; the owner's choice, 2026-11-24). From `web/`:

| Change | Command | Then |
|---|---|---|
| Colours, radius, font (the CSS) | `pnpm dlx shadcn-vue@2.9.0 init --preset <code> --force`, which keeps the components, as shadcn-vue's customization guide gives it | `pnpm format`; remove the Google Fonts import it adds (the Content-Security-Policy refuses it and Inter is bundled); set again the board's values `theme.test.ts` reports |
| The style (the components' look) | `pnpm dlx shadcn-vue@2.9.0 apply <code> --yes`, which re-installs every component | As above, then merge each file of `components/ui` three ways: the committed file, the CLI's output of the old style (an `apply` of the old code in a scratch worktree) as the base, the new output. That carries over what the board added: the casts `exactOptionalPropertyTypes` needs, the `success`, `warning` and `info` Badge variants, the indeterminate Checkbox. An icon the registry writes as a tag (`<SearchIcon />`) becomes `HugeiconsIcon` |

The board's own values sit in the same `:root` and `.dark` blocks, as the guide adds a colour (one
CSS file, never a second): the status colours, the eight categorical colours, the 6 px radius, and
the contrast fixes WCAG asks where the preset falls short (listed below). A preset switch rewrites
the preset's own names, so `web/src/theme.test.ts` measures each again. In the dark theme no one
step of the preset's indigo holds both white text at 4.5:1 and a ring at 3:1 on a card, so the
primary takes its `0.511` step and the ring its `0.585` step.

The sidebar uses deep slate in both themes, with labeled navigation groups. A soft fill marks
the active row, and the icons use the same tone throughout. Work surfaces use a cool background,
tinted table headers, and compact metric cards. Board lanes use a light wash of their stage color.

Sign-in uses the same card and button styles as the board, with selectable commands in muted
rows. First-run setup uses the shared section, progress, item and field components. Its active
step uses a muted surface and the primary action.

What the board means by
a colour:

| Meaning | Token |
|---|---|
| Text, secondary text | `foreground`, `muted-foreground` |
| Page, card, quiet fill, rule | `background`, `card`, `muted`, `border` |
| The one primary action of a screen, a link, the focus ring | `primary` indigo (`Button` `default`), `ring` |
| Status colours | `success`, `warning` and `info` beside shadcn-vue's `destructive`, set for both themes in `web/src/styles/app.css` and mapped in `@theme inline`; each is at least 4.5:1 on the card and on its own badge wash (`web/src/theme.test.ts` holds the tokens) |
| Contrast | the preset's tokens, set over them only where WCAG asks: `--input` and `--ring` at least 3:1 on the page and a card (control borders and the focus ring), `--muted-foreground` at least 4.5:1 on the page, a card and `--muted`, `--destructive` at least 4.5:1 on its badge wash; `web/src/theme.test.ts` measures each in both themes |
| A status word | `StatusBadge`: its tone from the status map and its words from `statusWord` (sentence case; a word the map names reads its own, as `blocked` reads Waiting on you), both in `web/src/lib/status_tone.ts`; a status the map does not know takes `tone` and its own words, and a label made of a name (a delivery's agent) is shown as written. The tones are `Badge` variants from `TONE_VARIANTS`: done (finished, approved, merged) `success`, under way (working, running, an open pull request, checks running) `info`, waiting on someone (waiting, waiting on you, stale, uncommitted, conflict) `warning`, failed `destructive`, at rest (idle, ended, closed, draft) `outline`; `success`, `warning` and `info` in `components/ui/badge` are a neutral outline with a dot in the tone's colour and the word in `foreground` (colour always beside a word, never a dot alone); `destructive` keeps shadcn-vue's red tint so a failure stands out |
| A fixed word (a ticket's type and priority, a memory entry's kind) | in sentence case on screen, through `sentence` in `web/src/lib/format.ts`, wherever it shows (a card, a list cell, a select, a filter, a menu); the value sent and the address keep the word as it is; a label or a name people chose is shown as written |
| Status in plain text | an error `text-destructive`; a warning `text-foreground` among `text-muted-foreground`; success reads as plain text (the status colours are for badges and dots) |
| Categorical colours | `chart-1` to `chart-8`, one order (blue, orange, aqua, yellow, magenta, green, violet, red), each theme stepped for its own surface and checked for colour-blind separation; charts take them in series order |
| Stages | a hue of their own (`STAGE_DOT` in `web/src/lib/board.ts`): Spec `chart-7` violet, Build `chart-1` blue, Review `chart-4` yellow, Merged `chart-6` green; Released, off the board, `muted-foreground`; drawn as a `StageGlyph` (`web/src/components/StageGlyph.vue`, the same hues as `STAGE_TONE`) that fills as the work moves: Spec an empty ring, Build half filled, Review three quarters, Merged and Released a filled circle with a check; beside its word wherever a stage shows (column header, List, ticket header, hover card, Archive, activity) |
| Labels | `chart-1` to `chart-8`: a board's labels in name order take them in turn, so eight in view never share one; a label the board does not list keeps `labelColor`'s hash (`web/src/lib/labels.ts`, `web/src/lib/format.ts`) |
| The logo | the factory mark (`web/src/components/AppMark.vue`) in literal colours, the same in both themes |

## Type scale

One size per role. A size is set only together with its role's classes; `web/src/design.test.ts`
(`every_text_size_a_screen_sets_is_a_role`, with the roles in `web/src/test/typeRoles.ts`) fails
on any other size, or a size with a line height, outside the generated `components/ui` files and
the `/design` samples.

| Role | Size |
|---|---|
| Page title (the header's `h1`) | `text-lg font-semibold`, the heading hook (sidebar-16) |
| Document title (a ticket's title, the sign-in card) | `text-lg font-semibold` |
| Section and card title | the component's own (`CardTitle`, `ItemTitle`, a section's `h2` at `text-base font-medium`) |
| Figure | `text-2xl font-semibold tabular-nums`; in a card `@[250px]/card:text-3xl` once the card is wide (dashboard-01); a missing figure `text-lg font-normal text-muted-foreground` |
| Text: body, rows, secondary and meta lines, table cells and headers | `text-sm`, secondary in `text-muted-foreground` (Vega's `ItemDescription`) |
| Caption: a group's label | `text-xs font-medium tracking-wider text-muted-foreground uppercase` |
| Code shown as a block (a diff's header, a command, a payload) | `font-mono text-xs` |
| Mono inline (ids, branches) | the size of the text around it (`a_mono_cell_takes_the_size_of_its_row`) |
| Controls and badges | the style's own sizes: `Button`, `Input`, `Tabs` at `text-sm`, `Badge` at `text-xs` |

Every number and amount is `tabular-nums`. Headings are Inter set tighter: `.cn-font-heading`
(the hook every generated title carries) adds `letter-spacing: -0.011em`. The one class that sets
type on a variant component is the table header's sort `Button` (`data-header-sort`), at the
header's `text-sm`.

Dark mode is the `dark` class on `<html>` alone: VueUse's `useColorMode` in `web/src/App.vue`,
saved under `codeFactoryTheme`, which `web/public/theme-early.js` reads before paint.

## Blocks

| Block | Where |
|---|---|
| sidebar-07 (a sidebar that collapses to icons) with the inset variant | the shell, `Sidebar collapsible="icon" variant="inset"` in `web/src/components/AppSidebar.vue`, the page a `SidebarInset` panel with a hairline border on the sidebar's background: folded, the icon column is `--sidebar-width-icon` at 2.5rem (set on the sidebar in `web/src/App.vue`, under the provider's 3rem default), so a button sits 16 px from either edge; no rail, the header's trigger, `[` or Cmd+B fold it |
| sidebar-16 (a sticky site header) | the header with the page title and its controls, the primary action last, in `web/src/App.vue` |
| dashboard-01 (section cards, the interactive area chart, the data table) | the Analytics tabs: tiles as section cards (`web/src/components/flow/FlowTiles.vue`, `web/src/components/factory/FactoryTiles.vue`), Shipped as the interactive area chart with the range control (`web/src/components/flow/PullsChart.vue`), the merged, stuck, runs and expensive lists as `DataTable`s in the Data Table example's bordered box, inside their section's `CardContent` |
| login-03 (a card on a muted background) | the signed-out screen, `web/src/components/SignInNotice.vue` |

Rendered Markdown (a ticket's documents, an agent's context) is Typeset: `typeset typeset-doc`,
the preset sized to the text around it (`web/src/styles/typeset.css`, `web/src/styles/app.css`).

## The board's own

| Part | Why shadcn-vue does not cover it |
|---|---|
| `page-wide` (`web/src/styles/app.css`) | Workspace pages use the full width with a shared inset. The page scroller reserves its scrollbar gutter on both edges and measures it into `--gutter` (`web/src/App.vue`). The page body gives it back from its side padding so each edge has the same inset. |
| `sortable-ghost`, `sortable-fallback` (`web/src/styles/app.css`) | SortableJS sets these classes on a dragged card |
| Domain components (`TicketCard`, `InboxRow`, `TeamTable`, `TraceRows`, ...) | They are the board's screens; each is built only from shadcn-vue's parts |
| `QuestionAsk` (`web/src/components/QuestionAsk.vue`) | One question answered in place, the same in the Inbox and on a ticket, in the shape `ask_question` takes: a topic chip, the question with Pick one or Pick any, then every choice as a card (`ChoiceCard`: its label, Recommended, its description, its preview as monospace code) with Other as the last card; one is picked (the recommended one to start with) or several ticked (Select all ticks every one), and Answer sends the pick, never a click on a card; with no choices the answer is typed. In the Inbox, a number key picks that choice and `a` answers; the page holding it sends and guards a second press. A click never sends: it leaves no moment to change one's mind |
| `PropertyShown` (`web/src/components/ticket/PropertyShown.vue`) | A ticket's property while it is edited: its value as a ghost `Button` that shows its own control opened in place; shadcn-vue has no quiet field, and restyling `Input` would set colours by class |
| `EmptyLine` (`web/src/components/EmptyLine.vue`) | An `Empty` inside a page's content laid out as one row (icon, then title and sentence), its title at a row title's `text-sm` so it never outranks the section heading over it; `SectionCard`'s empty slot and the ticket form's blocks use it, a page-wide `Empty` keeps shadcn-vue's layout |
| `CutText` (`web/src/components/CutText.vue`) | A single-line value (a branch, a label, a tool name) ends in an ellipsis and shows whole in a Tooltip; text that may wrap takes `wrap-anywhere`, so a hash breaks inside its box |
| `PageNav` (total, page, size, label) | `Pagination` (`web/src/components/PageNav.vue`) plus the range and the rows per page; every page is a link that keeps the address's other keys |
| Spans of time | one way on every page, `span` in `web/src/lib/format.ts` (`12s`, `30m`, `1.5h`, `4.2d`) |
| Where an empty state sits | inside its section, under its heading; a page with no section puts its `Empty` at the top of the page content, never centred in the viewport |
| An empty state's icon | it says which empty it is: `Tick02Icon` only when empty means nothing is wrong, `File01Icon` when a setting is still to do, `Wrench01Icon` for a part not built, else the page's sidebar icon |

## Tailwind

| Rule | Why |
|---|---|
| Every class is written whole in a component or `web/src/lib` (`bg-chart-1`, never a suffix joined to a prefix) | Tailwind builds only the names it finds in the source |
| No `@source inline()` safelist | A safelist drifts from the code |
| No inline script; inline styles are allowed | The Content-Security-Policy keeps `script-src 'self'`; `style-src 'self' 'unsafe-inline'` lets shadcn-vue's chart (Unovis) set its colours as style attributes and `<style>` elements |
