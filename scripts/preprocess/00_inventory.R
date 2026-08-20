#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
assert_free_space(cfg)

key <- "inventory"
with_failure_result(cfg, key, {
  started <- Sys.time()
  source_keys <- names(cfg$sources)
  paths <- vapply(source_keys, function(x) source_path(cfg, x), character(1L))
  missing <- paths[!file.exists(paths)]
  if (length(missing)) stop("Missing source files: ", paste(missing, collapse = ", "), call. = FALSE)

  info <- file.info(paths)
  inventory <- data.table(
    dataset = source_keys,
    path = paths,
    size_bytes = as.numeric(info$size),
    mtime = format(info$mtime, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"),
    sha256 = NA_character_,
    zip_crc = NA_character_
  )

  for (i in seq_len(nrow(inventory))) {
    path <- inventory$path[[i]]
    if (cli$mode == "production") {
      inventory$sha256[[i]] <- sha256_file(path)
      crc <- run_cmd("unzip", c("-tq", path), check = FALSE)
      inventory$zip_crc[[i]] <- if (crc$status == 0L) "PASS" else "FAIL"
      if (crc$status != 0L) stop("ZIP CRC failed: ", path, call. = FALSE)
    } else {
      inventory$sha256[[i]] <- "SMOKE_NOT_COMPUTED"
      inventory$zip_crc[[i]] <- "SMOKE_NOT_COMPUTED"
    }
  }

  inv_dir <- file.path(cfg$paths$staging_dir, "inventory")
  fwrite(inventory, file.path(inv_dir, sprintf("source_inventory_%s.csv", cli$mode)))
  write_json_atomic(inventory, file.path(inv_dir, sprintf("source_inventory_%s.json", cli$mode)))

  versions <- list(
    timestamp = kst_now(),
    mode = cli$mode,
    r = R.version.string,
    platform = R.version$platform,
    gdal = paste(capture_cmd("gdalinfo", "--version"), collapse = " "),
    ogr = paste(capture_cmd("ogr2ogr", "--version"), collapse = " "),
    proj = paste(head(capture_cmd("projinfo", "--version", check = FALSE), 2L), collapse = " "),
    config = cfg$config_path,
    config_sha256 = sha256_file(cfg$config_path),
    thesis_head = trimws(capture_cmd("git", c("-C", cfg$paths$thesis_repo, "rev-parse", "HEAD"))[[1L]]),
    fuse_head = trimws(capture_cmd("git", c("-C", cfg$paths$repo, "rev-parse", "HEAD"))[[1L]])
  )
  write_json_atomic(versions, file.path(inv_dir, sprintf("environment_%s.json", cli$mode)))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  write_marker(cfg, key, paste0(cli$mode, "_complete"), list(elapsed_sec = elapsed, files = nrow(inventory)))
  write_dataset_result(cfg, key, "PASS", list(mode = cli$mode, elapsed_sec = elapsed, files = nrow(inventory)))
  log_line(sprintf("INVENTORY_COMPLETE mode=%s files=%d elapsed_sec=%.3f", cli$mode, nrow(inventory), elapsed))
})

