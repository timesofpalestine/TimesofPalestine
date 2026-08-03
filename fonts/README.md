# Self-hosted webfonts

- `NotoKufiArabic-var.woff2` — Noto Kufi Arabic, variable weight 100–900,
  from Google Fonts (fonts.gstatic.com, Noto Kufi Arabic v27). Licensed
  under the SIL Open Font License 1.1
  (https://openfontlicense.org / https://fonts.google.com/noto/specimen/Noto+Kufi+Arabic/license).
  Chosen as the Arabic edition's primary face: it is the closest
  open-licensed match to Al Jazeera's exclusive custom typeface (Tarek
  Atrissi Design), which is legally restricted to Al Jazeera Network and
  must never be copied into this repo.

The build copies every `*.woff2` in this directory to `dist/fonts/` so the
site serves fonts same-origin, with no third-party requests from readers.
