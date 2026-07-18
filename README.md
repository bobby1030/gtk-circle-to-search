# GTK Circle to Search

A GTK 4 and Libadwaita application inspired by the "Circle to Search" feature in
Android. It allows you to select text from an image and perform actions such as 
searching or translating the selected text.

## Build

Python sources live under `src/`, while authored Blueprint templates live under
`data/ui/`. Meson compiles the templates, bundles the generated `.ui` files
into `circle-to-search.gresource`, and installs that bundle with the Python
package:

```sh
meson setup build
uv build
```

The build requires `meson`, `ninja`, `blueprint-compiler`, `libportal`, and
`libportal-gtk4`.

## Feature plan

### Implemented

- Run OCR asynchronously after showing the image.
- Open image files and capture interactive screenshots through libportal.
- Highlight recognized regions and support click or drag-area selection.
- Zoom the image with the scroll wheel.
- Show an animated OCR progress overlay and selection feedback.
- Combine multiple selected regions and display their average confidence.
- Edit recognized text in a multiline editor. Changes are committed on focus
  loss or with `Ctrl+Enter`; plain `Enter` inserts a new line.
- Copy recognized text and open a Google search in the default browser.
- Translate text asynchronously with the `translators` package.
- Choose searchable source and target languages, including automatic source
  detection by the translation provider.
- Enable or disable debounced automatic translation.
- Display multiline translation results, copy them, retry failures, and ignore
  stale asynchronous responses.

### Selection context

- [ ] Show the number of selected OCR regions.
- [ ] Warn when the selection contains low-confidence text.
- [ ] Add a clear-selection action.
- [ ] Show per-region confidence when reviewing a multi-region selection.

### Quick actions

- [ ] Detect URLs in recognized text and offer to open them directly.
- [ ] Save or export recognized text and translations.
- [ ] Add text-to-speech for recognized and translated text.
- [ ] Make sidebar actions configurable so rarely used actions can be hidden.

### OCR controls

- [ ] Re-run OCR without reopening the image.
- [ ] Choose the OCR language and model.
- [ ] Configure a minimum confidence threshold.
- [ ] Choose whether selected regions preserve lines or join into a paragraph.

### History and workflow

- [ ] Keep a small history of recent selections and translations.
- [ ] Restore a previous selection from history.
- [ ] Add an image chooser and drag-and-drop image loading.
- [ ] Persist sidebar width, language choices, and automatic-translation state.

## Current limitation

Images can be opened from the command line, but the in-app image chooser is
not implemented yet.
