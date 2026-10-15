# The plugin reaches 2.0 before the web companion

The owner's decision, 2026-10-15. It changes the product order of 2026-10-13 in
[versioning.md](../versioning.md).

An October 2026 review of the plugin, other coaching apps and how expert coaches work found more coaching to do in
the plugin than fits in 1.x without changing the targets it gives: stalls decided by a script and driving swaps and
easy weeks, a possible cap on load jumps from "reps left", measured numbers from progress photos, posture notes and
openGym both ways. A change to the targets is a major version, and this repository is the plugin
([ADR 0011](0011-repo-is-the-plugin.md)). So the plugin takes 2.0 on its own.

- **2.0 "Bellerophon"** is the plugin's measured coach. The plan is in the [roadmap](../roadmap.md).
- Each companion product moves up one major: **3.0 "Cadmus"** the web companion and the open sync server,
  **4.0 "Diomedes"** the iPhone companion, **5.0 "Enkidu"** the iPhone and Apple Watch logger.
- The hero table does not change: one hero per major, A to Z.

Consequences:
- The apps follow 2.0's new shared target cases before they ship as 2.x; until then they stay on the Achilles
  rules (one major across all products).
- [ADR 0006](0006-plugin-is-the-brain.md) still stands: the plugin is the brain, one sync format, the link is the
  user's choice.
- Several 2.0 items wait on gates of their own: the lawyer's review of the photo wording, ADRs for photo measures
  and for writing to openGym, and an evidence review on reps-left accuracy.
