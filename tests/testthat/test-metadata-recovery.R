testthat::test_that("metadata recovery rejects incomplete, foreign, stale, and colliding bundles", {
  root <- tempfile("metadata-recovery-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  implementation <- file.path(root, "implementation.py")
  writeLines("accepted", implementation)
  bundle <- file.path(root, "bundle")
  dir.create(bundle)
  output <- file.path(bundle, "payload.bin")
  writeBin(charToRaw("payload"), output)
  manifest <- file.path(bundle, "manifest.json")
  jsonlite::write_json(list(status = "PASS", artifact_id = "id_ok", parent_id = "parent_ok",
                            scientific = list(implementation_sha256 = metadata_recovery_sha256(implementation))),
                       manifest, auto_unbox = TRUE)
  spec <- list(id = "id_ok", manifest = "manifest.json", manifest_sha256 = metadata_recovery_sha256(manifest),
               status = "PASS", id_field = "artifact_id", parents = "parent_ok",
               files = c(manifest.json = metadata_recovery_sha256(manifest), payload.bin = metadata_recovery_sha256(output)),
               hashes = c("scientific.implementation_sha256" = implementation))
  testthat::expect_setequal(basename(validate_metadata_recovery_bundle("fixture", bundle, spec)), names(spec$files))

  file.remove(output)
  testthat::expect_error(validate_metadata_recovery_bundle("fixture", bundle, spec), "file-set mismatch")
  writeBin(charToRaw("payload"), output)
  writeLines("foreign", file.path(bundle, "foreign.bin"))
  testthat::expect_error(validate_metadata_recovery_bundle("fixture", bundle, spec), "file-set mismatch")
  file.remove(file.path(bundle, "foreign.bin"))

  foreign <- spec
  foreign$parents <- "foreign_parent"
  testthat::expect_error(validate_metadata_recovery_bundle("fixture", bundle, foreign), "foreign/missing parent")
  writeLines("stale", implementation)
  testthat::expect_error(validate_metadata_recovery_bundle("fixture", bundle, spec), "stale implementation/config/schema")
  writeLines("accepted", implementation)
  writeBin(charToRaw("different"), output)
  testthat::expect_error(validate_metadata_recovery_bundle("fixture", bundle, spec), "checksum mismatch")
})
