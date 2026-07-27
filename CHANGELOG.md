# Changelog

Versions are the `version` field in `.claude-plugin/plugin.json`. Because that field is set, an installed plugin only picks up changes when it **changes** — pushing to `main` alone ships nothing. CI enforces the bump.

## 1.0.1

- **Install now points at `trinity-ai-labs/claude-plugins`.** The marketplace catalogue used to live inside `orchestration-skills`, so installing these skills meant adding an unrelated plugin's repo as a marketplace first. The catalogue moved to a repo that ships no plugin of its own. The marketplace *name* is unchanged, so `frameworks@trinity-ai-labs` still resolves — only the `marketplace add` line moves.

## 1.0.0

First release. The `effect-v3` and `solid` reference skills, previously two separate repos installed by shell script, packaged as one plugin.

- De-identified: examples that were grounded in a specific product now say **the reference app**, including the code identifiers and source paths that named it even after the prose was generic.
- Every reference chapter over 300 lines gained a `## Contents` index, so a chapter can be scanned before it is read in full.
