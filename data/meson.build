subdir('ui')

install_data(
  'com.github.circle-to-search.desktop',
  install_dir: get_option('datadir') / 'applications',
)

install_data(
  'icons/hicolor/512x512/apps/com.github.circle-to-search.png',
  install_dir: get_option('datadir') / 'icons/hicolor/512x512/apps',
)

gnome.compile_resources(
  'circle-to-search',
  'com.github.circle_to_search.gresource.xml',
  dependencies: compiled_blueprints,
  source_dir: [
    meson.current_build_dir(),
    meson.current_source_dir(),
  ],
  gresource_bundle: true,
  install: true,
  install_dir: python.get_install_dir() / 'gtk_circle_to_search',
)
