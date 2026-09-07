list_p11_diagnostic_probes <- list(
  targets::tar_target(
    s11_diagnostic_sources,
    p11_diagnostic_source_files(),
    format = "file"
  ),
  targets::tar_target(
    s11_diagnostic_acceptance,
    {
      status <- system2(
        "python",
        c("scripts/p11_diagnostic_probes.py", "--config",
          p11_source_file(s11_diagnostic_sources, "p11_diagnostic_probe_matrix.yml")),
        stdout = TRUE,
        stderr = TRUE,
        env = c("PYTHONPATH=python", "PYTHONDONTWRITEBYTECODE=1")
      )
      if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"))
      result <- jsonlite::fromJSON(status[[length(status)]])
      file.path(
        "/mnt/hdd002/dhnyu/fusedata/downstream_data/p11_diagnostics",
        result$acceptance_id,
        "p11_g_acceptance.json"
      )
    },
    format = "file"
  )
)
