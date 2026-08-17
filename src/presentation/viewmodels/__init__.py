"""Intentionally empty.

AUDIOBOOKER_SPECS.md §41 suggests a presentation/viewmodels/ layer, but also
allows adapting the structure when another organization makes more sense.
For this MVP's screen count and complexity, a separate viewmodel layer added
indirection without benefit: each widget in presentation/widgets/ already
holds no business logic itself (it only calls application/ services through
presentation/workers/ background threads and renders their results) — the
widget's public getters (e.g. BookScreen.narration_settings(),
ChapterListWidget.chapters()) fill the role a viewmodel would. Kept as an
empty package for structural fidelity with the suggested layout; revisit if
a screen's state management grows complex enough to warrant extracting it.
"""
