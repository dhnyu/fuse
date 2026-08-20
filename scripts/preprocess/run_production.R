#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)

scripts <- c("00_inventory.R", "01_building.R", "02_road.R", "03_poi.R", "04_landcover.R", "05_dem.R", "06_validate.R")
status <- data.table(script = scripts, started_at = NA_character_, finished_at = NA_character_, exit_code = NA_integer_)
for (i in seq_along(scripts)) {
  script <- file.path(repo_root(), "scripts", "preprocess", scripts[[i]])
  status$started_at[[i]] <- kst_now()
  log_line(sprintf("PIPELINE_STEP_START index=%d/%d script=%s mode=%s", i, length(scripts), scripts[[i]], cli$mode))
  result <- run_cmd("Rscript", c(script, paste0("--mode=", cli$mode), paste0("--config=", cli$config)), check = FALSE)
  status$finished_at[[i]] <- kst_now()
  status$exit_code[[i]] <- result$status
  fwrite(status, file.path(cfg$paths$staging_dir, "qc", sprintf("pipeline_status_%s.csv", cli$mode)))
  if (result$status != 0L) log_line(sprintf("PIPELINE_STEP_FAILED script=%s status=%d; continuing independent datasets", scripts[[i]], result$status), level = "ERROR")
  if (i == 1L && result$status != 0L) stop("Source inventory failed; no dataset processing is safe", call. = FALSE)
}
failed <- status[exit_code != 0L]
log_line(sprintf("PIPELINE_COMPLETE mode=%s failed_steps=%d", cli$mode, nrow(failed)))
quit(status = if (nrow(failed)) 1L else 0L, save = "no")
