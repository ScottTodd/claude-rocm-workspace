# PR Review: [sysdeps] Fix zstd symbol visibility and -Bsymbolic linking

* **PR:** [#4251](https://github.com/ROCm/TheRock/pull/4251)
* **Author:** stellaraccident (Stella Laurenzo)
* **Reviewed:** 2026-03-31
* **Status:** OPEN
* **Base:** `main` ← `users/stella/fix-zstd-bsymbolic`
* **Fixes:** Follow-up to [#4212](https://github.com/ROCm/TheRock/pull/4212), progress on [#4211](https://github.com/ROCm/TheRock/issues/4211)

---

## Summary

Fixes two issues with ROCm's bundled zstd shared library on Linux:
1. The `-Bsymbolic` flag from PR #4212 was missing `-Wl,` and never reached the linker
2. Internal symbols (FSE_*, XXH*, HUF_*, COVER_*, etc.) were exported due to default visibility

**Net changes:** +5 lines, -1 line across 1 file

---

## Overall Assessment

**✅ APPROVED** — Both fixes verified against CI-built artifacts.

**Strengths:**

- Fixes the `-Wl,-Bsymbolic` issue identified in our review of #4212
- Goes further with `-fvisibility=hidden` + explicit `*_VISIBLE=default` to reduce exported symbols
- Uses zstd's own CMake cache variables (`ZSTDLIB_VISIBLE`, `ZSTDERRORLIB_VISIBLE`, `ZDICTLIB_VISIBLE`) which are converted to `__attribute__((visibility("default")))` by zstd's `add_definition()` macro — clean integration with upstream

**Verification:**

Downloaded `sysdeps_lib_generic` from the CI run ([artifacts index](https://therock-ci-artifacts.s3.amazonaws.com/23771970963-linux/index.html), run 23771970963) and compared against the PR #4212 artifact (run 23674255041):

```
$ readelf -d librocm_sysdeps_zstd.so.1.5.7 | grep -i symbolic

# PR 4212 (before):
(no output)

# PR 4251 (after):
 0x0000000000000010 (SYMBOLIC)           0x0
 0x000000000000001e (FLAGS)              SYMBOLIC
```

`SYMBOLIC` is now present — confirming `-Wl,-Bsymbolic` reaches the linker.

Symbol count comparison (defined FUNC symbols in `.dynsym`, excluding UND):

| | PR 4212 | PR 4251 |
|---|---|---|
| Exported FUNC symbols | 388 | 187 |
| SYMBOLIC flag | absent | present |

### Removed symbols (201 — internal, now hidden)

<details>
<summary>Full list</summary>

```
COVER_best_destroy
COVER_best_finish
COVER_best_init
COVER_best_start
COVER_best_wait
COVER_checkTotalCompressedSize
COVER_computeEpochs
COVER_dictSelectionError
COVER_dictSelectionFree
COVER_dictSelectionIsError
COVER_selectDict
COVER_sum
COVER_warnOnSmallCorpus
divbwt
divsufsort
ERR_getErrorString
FSE_buildCTable_rle
FSE_buildCTable_wksp
FSE_buildDTable_wksp
FSE_compress_usingCTable
FSE_compressBound
FSE_decompress_wksp_bmi2
FSE_getErrorName
FSE_isError
FSE_NCountWriteBound
FSE_normalizeCount
FSE_optimalTableLog
FSE_optimalTableLog_internal
FSE_readNCount
FSE_readNCount_bmi2
FSE_versionNumber
FSE_writeNCount
HIST_add
HIST_count
HIST_count_simple
HIST_count_wksp
HIST_countFast
HIST_countFast_wksp
HIST_isError
HUF_buildCTable_wksp
HUF_cardinality
HUF_compress1X_repeat
HUF_compress1X_usingCTable
HUF_compress4X_repeat
HUF_compress4X_usingCTable
HUF_compressBound
HUF_decompress1X_DCtx_wksp
HUF_decompress1X_usingDTable
HUF_decompress1X1_DCtx_wksp
HUF_decompress1X2_DCtx_wksp
HUF_decompress4X_hufOnly_wksp
HUF_decompress4X_usingDTable
HUF_estimateCompressedSize
HUF_getErrorName
HUF_getNbBitsFromCTable
HUF_isError
HUF_minTableLog
HUF_optimalTableLog
HUF_readCTable
HUF_readCTableHeader
HUF_readDTableX1_wksp
HUF_readDTableX2_wksp
HUF_readStats
HUF_readStats_wksp
HUF_selectDecoder
HUF_validateCTable
HUF_writeCTable_wksp
POOL_add
POOL_create
POOL_create_advanced
POOL_free
POOL_joinJobs
POOL_resize
POOL_sizeof
POOL_tryAdd
ZSTD_buildBlockEntropyStats
ZSTD_buildCTable
ZSTD_buildFSETable
ZSTD_CCtx_trace
ZSTD_checkContinuity
ZSTD_compress_advanced_internal
ZSTD_compressBegin_advanced_internal
ZSTD_compressBegin_usingCDict_deprecated
ZSTD_compressBlock_btlazy2
ZSTD_compressBlock_btlazy2_dictMatchState
ZSTD_compressBlock_btlazy2_extDict
ZSTD_compressBlock_btopt
ZSTD_compressBlock_btopt_dictMatchState
ZSTD_compressBlock_btopt_extDict
ZSTD_compressBlock_btultra
ZSTD_compressBlock_btultra_dictMatchState
ZSTD_compressBlock_btultra_extDict
ZSTD_compressBlock_btultra2
ZSTD_compressBlock_deprecated
ZSTD_compressBlock_doubleFast
ZSTD_compressBlock_doubleFast_dictMatchState
ZSTD_compressBlock_doubleFast_extDict
ZSTD_compressBlock_fast
ZSTD_compressBlock_fast_dictMatchState
ZSTD_compressBlock_fast_extDict
ZSTD_compressBlock_greedy
ZSTD_compressBlock_greedy_dedicatedDictSearch
ZSTD_compressBlock_greedy_dedicatedDictSearch_row
ZSTD_compressBlock_greedy_dictMatchState
ZSTD_compressBlock_greedy_dictMatchState_row
ZSTD_compressBlock_greedy_extDict
ZSTD_compressBlock_greedy_extDict_row
ZSTD_compressBlock_greedy_row
ZSTD_compressBlock_lazy
ZSTD_compressBlock_lazy_dedicatedDictSearch
ZSTD_compressBlock_lazy_dedicatedDictSearch_row
ZSTD_compressBlock_lazy_dictMatchState
ZSTD_compressBlock_lazy_dictMatchState_row
ZSTD_compressBlock_lazy_extDict
ZSTD_compressBlock_lazy_extDict_row
ZSTD_compressBlock_lazy_row
ZSTD_compressBlock_lazy2
ZSTD_compressBlock_lazy2_dedicatedDictSearch
ZSTD_compressBlock_lazy2_dedicatedDictSearch_row
ZSTD_compressBlock_lazy2_dictMatchState
ZSTD_compressBlock_lazy2_dictMatchState_row
ZSTD_compressBlock_lazy2_extDict
ZSTD_compressBlock_lazy2_extDict_row
ZSTD_compressBlock_lazy2_row
ZSTD_compressContinue_public
ZSTD_compressEnd_public
ZSTD_compressLiterals
ZSTD_compressRleLiteralsBlock
ZSTD_compressSuperBlock
ZSTD_convertBlockSequences
ZSTD_copyDDictParameters
ZSTD_crossEntropyCost
ZSTD_cycleLog
ZSTD_DDict_dictContent
ZSTD_DDict_dictSize
ZSTD_decodeLiteralsBlock_wrapper
ZSTD_decodeSeqHeaders
ZSTD_decompressBlock_deprecated
ZSTD_decompressBlock_internal
ZSTD_dedicatedDictSearch_lazy_loadDictionary
ZSTD_encodeSequences
ZSTD_fillDoubleHashTable
ZSTD_fillHashTable
ZSTD_fseBitCost
ZSTD_get1BlockSummary
ZSTD_getcBlockSize
ZSTD_getCParamsFromCCtxParams
ZSTD_getCParamsFromCDict
ZSTD_getSeqStore
ZSTD_initCStream_internal
ZSTD_insertAndFindFirstIndex
ZSTD_invalidateRepCodes
ZSTD_ldm_adjustParameters
ZSTD_ldm_blockCompress
ZSTD_ldm_fillHashTable
ZSTD_ldm_generateSequences
ZSTD_ldm_getMaxNbSeq
ZSTD_ldm_getTableSize
ZSTD_ldm_skipRawSeqStoreBytes
ZSTD_ldm_skipSequences
ZSTD_loadCEntropy
ZSTD_loadDEntropy
ZSTD_noCompressLiterals
ZSTD_referenceExternalSequences
ZSTD_reset_compressedBlockState
ZSTD_resetSeqStore
ZSTD_row_update
ZSTD_selectBlockCompressor
ZSTD_selectEncodingType
ZSTD_seqToCodes
ZSTD_splitBlock
ZSTD_updateTree
ZSTD_writeLastEmptyBlock
ZSTD_XXH_versionNumber
ZSTD_XXH32
ZSTD_XXH32_canonicalFromHash
ZSTD_XXH32_copyState
ZSTD_XXH32_createState
ZSTD_XXH32_digest
ZSTD_XXH32_freeState
ZSTD_XXH32_hashFromCanonical
ZSTD_XXH32_reset
ZSTD_XXH32_update
ZSTD_XXH64
ZSTD_XXH64_canonicalFromHash
ZSTD_XXH64_copyState
ZSTD_XXH64_createState
ZSTD_XXH64_digest
ZSTD_XXH64_freeState
ZSTD_XXH64_hashFromCanonical
ZSTD_XXH64_reset
ZSTD_XXH64_update
ZSTDMT_compressStream_generic
ZSTDMT_createCCtx_advanced
ZSTDMT_freeCCtx
ZSTDMT_getFrameProgression
ZSTDMT_initCStream_internal
ZSTDMT_nextInputSizeHint
ZSTDMT_sizeof_CCtx
ZSTDMT_toFlushNow
ZSTDMT_updateCParams_whileCompressing
```

</details>

### Kept symbols (187 — public API)

<details>
<summary>Full list</summary>

```
ZDICT_addEntropyTablesFromBuffer
ZDICT_finalizeDictionary
ZDICT_getDictHeaderSize
ZDICT_getDictID
ZDICT_getErrorName
ZDICT_isError
ZDICT_optimizeTrainFromBuffer_cover
ZDICT_optimizeTrainFromBuffer_fastCover
ZDICT_trainFromBuffer
ZDICT_trainFromBuffer_cover
ZDICT_trainFromBuffer_fastCover
ZDICT_trainFromBuffer_legacy
ZSTD_adjustCParams
ZSTD_CCtx_getParameter
ZSTD_CCtx_loadDictionary
ZSTD_CCtx_loadDictionary_advanced
ZSTD_CCtx_loadDictionary_byReference
ZSTD_CCtx_refCDict
ZSTD_CCtx_refPrefix
ZSTD_CCtx_refPrefix_advanced
ZSTD_CCtx_refThreadPool
ZSTD_CCtx_reset
ZSTD_CCtx_setCParams
ZSTD_CCtx_setFParams
ZSTD_CCtx_setParameter
ZSTD_CCtx_setParametersUsingCCtxParams
ZSTD_CCtx_setParams
ZSTD_CCtx_setPledgedSrcSize
ZSTD_CCtxParams_getParameter
ZSTD_CCtxParams_init
ZSTD_CCtxParams_init_advanced
ZSTD_CCtxParams_registerSequenceProducer
ZSTD_CCtxParams_reset
ZSTD_CCtxParams_setParameter
ZSTD_checkCParams
ZSTD_compress
ZSTD_compress_advanced
ZSTD_compress_usingCDict
ZSTD_compress_usingCDict_advanced
ZSTD_compress_usingDict
ZSTD_compress2
ZSTD_compressBegin
ZSTD_compressBegin_advanced
ZSTD_compressBegin_usingCDict
ZSTD_compressBegin_usingCDict_advanced
ZSTD_compressBegin_usingDict
ZSTD_compressBlock
ZSTD_compressBound
ZSTD_compressCCtx
ZSTD_compressContinue
ZSTD_compressEnd
ZSTD_compressSequences
ZSTD_compressSequencesAndLiterals
ZSTD_compressStream
ZSTD_compressStream2
ZSTD_compressStream2_simpleArgs
ZSTD_copyCCtx
ZSTD_copyDCtx
ZSTD_cParam_getBounds
ZSTD_createCCtx
ZSTD_createCCtx_advanced
ZSTD_createCCtxParams
ZSTD_createCDict
ZSTD_createCDict_advanced
ZSTD_createCDict_advanced2
ZSTD_createCDict_byReference
ZSTD_createCStream
ZSTD_createCStream_advanced
ZSTD_createDCtx
ZSTD_createDCtx_advanced
ZSTD_createDDict
ZSTD_createDDict_advanced
ZSTD_createDDict_byReference
ZSTD_createDStream
ZSTD_createDStream_advanced
ZSTD_createThreadPool
ZSTD_CStreamInSize
ZSTD_CStreamOutSize
ZSTD_DCtx_getParameter
ZSTD_DCtx_loadDictionary
ZSTD_DCtx_loadDictionary_advanced
ZSTD_DCtx_loadDictionary_byReference
ZSTD_DCtx_refDDict
ZSTD_DCtx_refPrefix
ZSTD_DCtx_refPrefix_advanced
ZSTD_DCtx_reset
ZSTD_DCtx_setFormat
ZSTD_DCtx_setMaxWindowSize
ZSTD_DCtx_setParameter
ZSTD_decodingBufferSize_min
ZSTD_decompress
ZSTD_decompress_usingDDict
ZSTD_decompress_usingDict
ZSTD_decompressBegin
ZSTD_decompressBegin_usingDDict
ZSTD_decompressBegin_usingDict
ZSTD_decompressBlock
ZSTD_decompressBound
ZSTD_decompressContinue
ZSTD_decompressDCtx
ZSTD_decompressionMargin
ZSTD_decompressStream
ZSTD_decompressStream_simpleArgs
ZSTD_defaultCLevel
ZSTD_dParam_getBounds
ZSTD_DStreamInSize
ZSTD_DStreamOutSize
ZSTD_endStream
ZSTD_estimateCCtxSize
ZSTD_estimateCCtxSize_usingCCtxParams
ZSTD_estimateCCtxSize_usingCParams
ZSTD_estimateCDictSize
ZSTD_estimateCDictSize_advanced
ZSTD_estimateCStreamSize
ZSTD_estimateCStreamSize_usingCCtxParams
ZSTD_estimateCStreamSize_usingCParams
ZSTD_estimateDCtxSize
ZSTD_estimateDDictSize
ZSTD_estimateDStreamSize
ZSTD_estimateDStreamSize_fromFrame
ZSTD_findDecompressedSize
ZSTD_findFrameCompressedSize
ZSTD_flushStream
ZSTD_frameHeaderSize
ZSTD_freeCCtx
ZSTD_freeCCtxParams
ZSTD_freeCDict
ZSTD_freeCStream
ZSTD_freeDCtx
ZSTD_freeDDict
ZSTD_freeDStream
ZSTD_freeThreadPool
ZSTD_generateSequences
ZSTD_getBlockSize
ZSTD_getCParams
ZSTD_getDecompressedSize
ZSTD_getDictID_fromCDict
ZSTD_getDictID_fromDDict
ZSTD_getDictID_fromDict
ZSTD_getDictID_fromFrame
ZSTD_getErrorCode
ZSTD_getErrorName
ZSTD_getErrorString
ZSTD_getFrameContentSize
ZSTD_getFrameHeader
ZSTD_getFrameHeader_advanced
ZSTD_getFrameProgression
ZSTD_getParams
ZSTD_initCStream
ZSTD_initCStream_advanced
ZSTD_initCStream_srcSize
ZSTD_initCStream_usingCDict
ZSTD_initCStream_usingCDict_advanced
ZSTD_initCStream_usingDict
ZSTD_initDStream
ZSTD_initDStream_usingDDict
ZSTD_initDStream_usingDict
ZSTD_initStaticCCtx
ZSTD_initStaticCDict
ZSTD_initStaticCStream
ZSTD_initStaticDCtx
ZSTD_initStaticDDict
ZSTD_initStaticDStream
ZSTD_insertBlock
ZSTD_isError
ZSTD_isFrame
ZSTD_isSkippableFrame
ZSTD_maxCLevel
ZSTD_mergeBlockDelimiters
ZSTD_minCLevel
ZSTD_nextInputType
ZSTD_nextSrcSizeToDecompress
ZSTD_readSkippableFrame
ZSTD_registerSequenceProducer
ZSTD_resetCStream
ZSTD_resetDStream
ZSTD_sequenceBound
ZSTD_sizeof_CCtx
ZSTD_sizeof_CDict
ZSTD_sizeof_CStream
ZSTD_sizeof_DCtx
ZSTD_sizeof_DDict
ZSTD_sizeof_DStream
ZSTD_toFlushNow
ZSTD_versionNumber
ZSTD_versionString
ZSTD_writeSkippableFrame
```

</details>

---

## Detailed Review

### 1. `-Wl,-Bsymbolic` fix

```cmake
-    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/version.lds -Bsymbolic"
+    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/version.lds -Wl,-Bsymbolic"
```

Correct. Now consistent with the `-Wl,--version-script` on the same line.

### 2. Visibility controls

```cmake
+    "-DCMAKE_C_FLAGS=-fvisibility=hidden"
+    -DZSTDLIB_VISIBLE=default
+    -DZSTDERRORLIB_VISIBLE=default
+    -DZDICTLIB_VISIBLE=default
```

This is the right approach:
- `-fvisibility=hidden` hides all symbols by default
- The three `*_VISIBLE=default` cache variables are processed by zstd's CMake `add_definition()` macro, which converts them to `-DZSTDLIB_VISIBLE=__attribute__((visibility("default")))` compile flags
- Only functions annotated with `ZSTDLIB_API`, `ZSTDERRORLIB_API`, or `ZDICTLIB_API` in zstd headers get exported

### 3. CI results

Linux foundation stage passed. All Linux build stages passed. Test failures (gfx1151 sanity, gfx94X hip-tests/rocblas/rocgdb, gfx94X python devel wheels) appear unrelated to this change — they're in GPU test jobs, not the foundation build where zstd lives.

### 📋 FUTURE WORK: Audit other bundled libraries

The parent issue [#4211](https://github.com/ROCm/TheRock/issues/4211) tracks auditing all sysdeps libraries. Other shared libraries under `third-party/sysdeps/` with `version.lds` may need the same `-Wl,-Bsymbolic` + visibility treatment.

---

## Recommendations

### 📋 Future Follow-up:

1. Audit other sysdeps shared libraries for the same interposition risk (tracked in #4211)
2. Consider a CI validation step that checks for `SYMBOLIC` in the dynamic section of all bundled `.so` files to prevent regressions

---

## Conclusion

**Approval Status: ✅ APPROVED**

Both fixes are verified by artifact inspection: `SYMBOLIC` flag is present in the dynamic section, and exported symbols dropped from 388 to 187 (only public `ZSTD_*`/`ZDICT_*`/`ZSTD_ERROR_*` API). The approach cleanly uses zstd's upstream CMake visibility variables rather than patching headers.
