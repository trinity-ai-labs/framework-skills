# Changelog

Versions are the `version` field in `.claude-plugin/plugin.json`. Because that field is set, an installed plugin only picks up changes when it **changes** — pushing to `main` alone ships nothing. CI enforces the bump.

## 1.0.0

First release. The `effect-v3` and `solid` reference skills, previously two separate repos installed by shell script, packaged as one plugin.

- De-identified: examples that were grounded in a specific product now say **the reference app**, including the code identifiers and source paths that named it even after the prose was generic.
- Every reference chapter over 300 lines gained a `## Contents` index, so a chapter can be scanned before it is read in full.
