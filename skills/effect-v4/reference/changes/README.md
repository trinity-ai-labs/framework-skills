# Generated release changes

Each `<version>.md` here is written by `python3 tools/api-snapshot/api_snapshot.py watch` (run daily by the
`effect-release-watch` workflow) when a new `effect` release appears on npm. It lists what that release removed or
changed, unstable and experimental exports first and stable ones separately, against the previous committed
snapshot in `api/effect/`. The two versions it compares are named at the top of each file.

Do not edit these files by hand. To regenerate one, delete it and run the command above, or write it with `api_snapshot.py changes <earlier.json> <later.json>`; `watch` never overwrites an existing file.
They carry no `verified` stamp and the symbol check does not read them.
