import type { KnipConfig } from 'knip'

export default {
  // Nothing imports the answer goldens: the type check reads them, failing when the server's
  // answers and the app's types disagree.
  // shadcn-vue's CLI imports `cn` from lib/utils.ts, the `aliases.utils` of web/components.json, in
  // the components it adds; its docs make it the one place the board's own code takes `cn` from.
  // Each shadcn-vue component's index.ts is the component's API as its CLI writes it; the parts the
  // board does not use yet stay exported.
  entry: ['src/generated/answers.ts', 'src/lib/utils.ts', 'src/components/ui/*/index.ts'],
  // The README's recordings (web/demo) turn videos into GIFs with the system's ffmpeg, which no
  // npm package provides.
  ignoreBinaries: ['ffmpeg'],
} satisfies KnipConfig
