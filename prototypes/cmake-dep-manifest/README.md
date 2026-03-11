# Option A: CMake-emitted dependency manifest

Sketch for having CMake emit a `therock_subproject_deps.json` file at
configure time, containing the fully-resolved subproject dependency graph.

## Files

- `therock_subproject.cmake.patch` — CMake changes (diff-style description)
- `therock_subproject_deps_example.json` — example output
- `query_subproject_deps.py` — Python consumer script

## How it works

1. `therock_cmake_subproject_declare()` appends each subproject's name,
   BUILD_DEPS, and RUNTIME_DEPS to a global property
   (`THEROCK_SUBPROJECT_DEPENDENCY_ENTRIES`).

2. A new `therock_subproject_write_dependency_manifest()` function (called
   from the top-level CMakeLists.txt alongside
   `therock_subproject_merge_compile_commands()`) reads the global property
   and writes a JSON file to `${CMAKE_BINARY_DIR}/therock_subproject_deps.json`.

3. A Python script reads the JSON and answers dependency queries (which
   packages to test, reverse deps, etc.).

## Design notes

- Uses the same global-property-accumulate-then-finalize pattern as
  compile_commands merging.
- All variable resolution happens in CMake (where it belongs).
- The JSON file is a build artifact — it's regenerated on every configure,
  so it's always in sync with the CMakeLists.txt files.
- The Python consumer has zero CMake parsing logic.
