blueprint_compiler = find_program('blueprint-compiler', required: true)

blueprint_sources = files(
  'main-window.blp',
  'translator-pane.blp',
)

compiled_blueprints = custom_target(
  'compile-blueprints',
  input: blueprint_sources,
  output: [
    'main-window.ui',
    'translator-pane.ui',
  ],
  command: [
    blueprint_compiler,
    'batch-compile',
    '--minify',
    '@OUTDIR@',
    '@CURRENT_SOURCE_DIR@',
    '@INPUT@',
  ],
  build_by_default: true,
)
