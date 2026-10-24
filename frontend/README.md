# VulHawk pitch website

**VulHawk** is the product and team name.

A responsive, buildless frontend for the Night Shift × Mubit security guard pitch.

## Preview

Serve `dist/` using a static HTTP server, for example:

```sh
python3 -m http.server 4173 --directory dist
```

## Included

- Product positioning and commercial narrative.
- Three interactive, explicitly scripted walkthroughs.
- Clickable current / proposed system architecture.
- Editable time-value calculator with transparent assumptions.
- A dedicated six-slide pitch deck at `dist/pitch.html`, with keyboard navigation, overview, fullscreen and print/PDF support.
- Short presentation copy, with detailed rationale and sources in presenter notes (Notes button or N).
- System architecture and Mubit training diagrams on slides 3–4, followed by buyer/revenue and pilot scorecard slides.
- A locally generated, downloadable pilot brief. No lead information is submitted.
- Responsive layouts, keyboard controls, reduced-motion support and native modal dialogs.

## Product accuracy

This is a presentation frontend, not a connected security scanner. It calls no models or paid APIs and stores no secrets. The current provider-based hook is separated from the planned correction / adapter integration. No customer, measured performance or savings claims are fabricated.

Project source: https://github.com/keerthanenr/mubit-sec-guard

Mubit documentation: https://docs.mubit.ai/guides/first-adapter and https://docs.mubit.ai/guides/model-ids

Google Fonts is optional; system font fallbacks are provided. Everything else is served locally.
