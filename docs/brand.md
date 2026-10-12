# Brand

The CoAIch look, made official on 2026-10-12 ([ADR 0007](adr/0007-plasma-brand.md)). One brand colour, **Plasma
fuchsia**, on ink and bone. Everything public (this repo, the web, the apps' default theme) follows this page.

## Colour

| Token | Hex | Use | Contrast |
|---|---|---|---|
| Plasma (dark) | `#F05AD8` | Accent on ink: wordmark, links, key numbers, the reason line's arrow | 6.75:1 on ink |
| Plasma (light) | `#A61E93` | The same roles on bone or white. Plasma itself fails on light (2.6:1) | 5.77:1 on bone |
| Ink | `#0A0A0B` | Dark ground, text on light | 17.5:1 with bone |
| Bone | `#F4F1EA` | Light ground: README, documents, posts | |
| Stone | `#B7B1A5` / `#5E5A52` | Secondary text on ink / on bone | 9.3:1 / 6.1:1 |

Rules:
- **One accent.** Plasma is line and type, never a large soft fill. A Plasma fill always carries a **black** label,
  never white.
- **Meaning colours never move:** done green, fail red, rest amber, drop-set violet. The brand never borrows them,
  and state is always text + glyph + colour, never colour alone.
- **No gradients, no glow, no sparkles.** Screens on ink; documents on bone.
- Every public image carries the reason line (`▲ +2.5 kg · because …`) and Plasma.

## Type

- **Titles:** Archivo ExtraCondensed, weight 800, capitals.
- **Text:** Archivo, normal width, 400–600.
- **Numbers in tables and logs:** a monospace font.
- Archivo is under the SIL Open Font License. In images for GitHub, text is outlined (turned into shapes), since a
  README can't load fonts.

## Logo and wordmark

**The logo is the Cut C** (chosen 2026-10-12): a heavy, condensed C cut by one horizontal line, the line under
every reason. Rounded outside corners, square inside corners.

- **Wordmark (2026-10-12):** **CoAIch**, spelled as the name is written. The Cut C is the capital C; then
  "o", "AI" and "ch" in Archivo ExtraCondensed 800, one colour. The capitals show the AI, and **the logo's cut runs
  through the AI** at mid-height, its lower half stepped right, so the AI is set apart by our own mark, not by colour.
- **Animation (README banner only):** the cut opens once when the page loads, then holds. Readers who ask their
  system for less motion see the still version.
- **On its own** (app icon, avatar, favicon): the Cut C alone, Plasma on ink or `#A61E93` on bone.
- **Below 24 px** the cut gets thin; check it on the real screen before using it that small.

Files in `docs/brand/`: `wordmark-ink.svg`, `wordmark-bone.svg`, `logo-ink.svg`, `logo-bone.svg`, `logo-mono.svg`, `app-icon.svg`, `banner-light.svg`,
`banner-dark.svg`, `social-preview.png` (1280 × 640, for the repository's social preview).

## Voice

Plain and calm. Every recommendation ends in a choice the lifter owns: keep, apply, edit. "Change nothing" is a
valid answer. Never "AI-powered", "smart", "guaranteed" or "no guesswork".
