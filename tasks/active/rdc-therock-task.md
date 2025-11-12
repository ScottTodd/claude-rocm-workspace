# Adapt RDC to build for manylinux in TheRock

**Status:** Not started
**Priority:** P1 (High)

## Overview

Source for RDC are at `/develop/therock/rocm-systems/projects/rdc` and it is set to be integrated into TheRock. However, no design/approach has been worked out for how to do so. Naively just trying to vendor grpc and such for manylinux compatibility is not simple or easily supportable. We need to come up with a design for producing a self-contained portable build of RDC, and then we need to integrate it into TheRock.

Unlike other libraries that are already in TheRock, this one has a couple of special points:

* It is primarily a tool vs a core library: we don't need to have shared/distributed dependent libraries so long as we can static link or properly isolate its heavier libraries (like grpc and its deps).
* It has integrated python bindings and we don't know what style (ctypes, pybind, etc). Need to decide whether we need to do multi-python builds, etc.
* We distribute an rdc wheel on pypi. I think right now, that is trying to link up with the rdc installation in /opt/rocm, but it really needs to be self contained and based on the same portable build as the version shipped as part of ROCm.
* RDC has an API but it is unclear if it is used and what the expectations are with respect to vendoring deps.

I would like a . Then I would like a next step to be to prototype build scripts that produce this portable build, given a base ROCm install. 

## Goals

- [x] comprehensive analysis of the codebase and a design doc with a recommendation and alternatives considered for creating a portable build of it
- [ ] a next step to be to prototype build scripts that produce this portable build
- [ ] setup.py / pyproject.toml that can build a standalone, portable wheel for rdc

## Implementation

### Files Created/Modified

- `/develop/therock/docs/rfcs/RFC0006-rdc-manylinux-integration.md` - Comprehensive RFC for RDC integration

### Key Details

- Performed deep analysis of RDC build artifacts and dependencies
- Documented that embedded mode needs ~2.2MB, standalone adds ~45MB of gRPC
- Identified gRPC v1.67.1 requirement due to Clang 18+ ABI compatibility
- Recommended phased approach: embedded-only first, defer gRPC decision
- Proposed using new `dctools/` directory in TheRock for datacenter tools
- Clarified that Python wheel can be version-agnostic due to ctypes


### Verification

### Committed

### Pull Request

### Next Steps (Post-Merge)

## Context

