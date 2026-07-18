subdir('ui')

install_data(
  'me.bobbyho.CircleToSearch.desktop',
  install_dir: get_option('datadir') / 'applications',
)

install_data(
  'icons/hicolor/scalable/apps/me.bobbyho.CircleToSearch.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
)

gnome.compile_resources(
  'me.bobbyho.CircleToSearch',
  'me.bobbyho.CircleToSearch.gresource.xml',
  dependencies: compiled_blueprints,
  source_dir: [
    meson.current_build_dir(),
    meson.current_source_dir(),
  ],
  gresource_bundle: true,
  install: true,
  install_dir: python.get_install_dir() / 'gtk_circle_to_search',
)
