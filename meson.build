project(
  'gtk-circle-to-search',
  version: '0.1.0',
  meson_version: '>=1.0.0',
)

python = import('python').find_installation('python3')
gnome = import('gnome')

subdir('src/gtk_circle_to_search')
subdir('data')

summary(
  {
    'Python': python.full_path(),
    'Blueprint compiler': blueprint_compiler.full_path(),
  },
  section: 'Build configuration',
)
