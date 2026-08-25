test_that("runtime checksum evidence is reused only while file identity is unchanged", {
  path <- tempfile()
  on.exit(unlink(path), add = TRUE)
  writeBin(charToRaw("accepted"), path)
  expected <- sha256_file(path)
  original <- sha256_file
  calls <- 0L
  assign("sha256_file", function(value) {
    calls <<- calls + 1L
    original(value)
  }, envir = environment(runtime_verified_sha256))
  on.exit(assign("sha256_file", original, envir = environment(runtime_verified_sha256)), add = TRUE)

  expect_identical(runtime_verified_sha256(path, expected), expected)
  expect_identical(runtime_verified_sha256(path, expected), expected)
  expect_identical(calls, 1L)

  Sys.sleep(0.01)
  writeBin(charToRaw("corrupt!"), path)
  expect_error(runtime_verified_sha256(path, expected), "checksum mismatch")
  expect_identical(calls, 2L)
})
