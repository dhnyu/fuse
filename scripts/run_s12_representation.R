#!/usr/bin/env Rscript
# Authorized future full execution only; never invoke the legacy evaluation graph.
stopifnot(length(commandArgs(trailingOnly = TRUE)) == 0L)
e <- jsonlite::read_json("config/s12_representation_alignment.json")$execution
if (!identical(Sys.getenv(e$authorization_env), e$authorization_value)) stop("S12 full execution is not authorized")
p <- Sys.getenv(e$pilot_receipt_env)
if (!nzchar(p) || !file.exists(p)) stop("S12 current passing pilot receipt required")
r <- jsonlite::read_json(p)
stopifnot(identical(r$status, "PASS"), identical(as.integer(Sys.getenv("FUSE_S12_WORKERS")), as.integer(r$recommended_workers)))
# Check current source/runtime/parent bindings even when targets are cached.
request <- tempfile(fileext = ".json")
writeLines("{}", request)
preflight <- system2(Sys.getenv("FUSE_PYTHON", "python"), c("scripts/s12_representation.py", "preflight", "--request", shQuote(request)), stdout = TRUE)
unlink(request)
if (!is.null(attr(preflight, "status")) && attr(preflight, "status") != 0L) stop("S12 preflight failed")
stopifnot(identical(jsonlite::fromJSON(tail(preflight, 1L))$status, "PASS"))
targets::tar_make(names = s12_scientific_acceptance, script = "_targets_representation_comparison.R",
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-s12-representation-alignment")
