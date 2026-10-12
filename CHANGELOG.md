# Changelog

What changed, newest first. The plugin keeps its own detailed changelog in
[plugin/CHANGELOG.md](plugin/CHANGELOG.md); this file covers the whole project. What's next is in the
[roadmap](docs/roadmap.md). Versions follow [docs/versioning.md](docs/versioning.md).

## Unreleased

## 0.3.0, preview

### Project
- Architecture written down ([ADR 0006](docs/adr/0006-plugin-is-the-brain.md)): the apps record and show, the plugin
  is the brain, and the link between them is the user's choice (a file, a local server, your own Cloudflare, or Pro later; one person per server),
  all on one open sync format. Diagram on the front page.
- Roadmap and this changelog.
- Plasma fuchsia made the official brand ([ADR 0007](docs/adr/0007-plasma-brand.md), [brand page](docs/brand.md)): banner,
  badges, diagrams in light and dark, social preview image. Sponsor button and a "Support CoAIch" section.
- Contributor guide, security policy, issue forms, pull request checklist, labels.
- Checks: files over 500 KB fail; releases need the tag, the plugin version and the changelog to agree.

### Plugin
- Photo review removes the face before Claude sees a photo; back views get a block over the head instead of a cut.
  Details in [plugin/CHANGELOG.md](plugin/CHANGELOG.md).

### Apps (alpha)
- The iPhone and Apple Watch code here is an early snapshot (2026-10-11) of the maintainer's alpha builds. It is
  not released and not meant for other people yet. The first public app version is Release 1.

## Plugin 0.2.0, preview
Nutrition, physique (photo review and priorities), monthly check-in, adapt and roadmap skills. See
[plugin/CHANGELOG.md](plugin/CHANGELOG.md).

## Plugin 0.1.0, preview
Onboarding with the medical gate, imports (Strong, Hevy, Apple Health), program build and audit, progression, and
the weekly review. See [plugin/CHANGELOG.md](plugin/CHANGELOG.md).
