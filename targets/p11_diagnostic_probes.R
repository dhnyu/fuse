list_p11_diagnostic_probes <- list(
  targets::tar_target(
    p11_g_contract,
    "config/p11_diagnostic_probe_matrix.yml",
    format = "file"
  ),
  targets::tar_target(
    p11_g_authorized_inputs,
    c(
      "config/p11_ridge_evaluation_acceptance.yml",
      "config/p11_spatial_readiness_acceptance.yml",
      "config/p11_target_transformation_methodology.json",
      "config/p11_downstream_dataset.yml"
    ),
    format = "file"
  ),
  targets::tar_target(
    p11_g_acceptance,
    {
      p11_g_authorized_inputs
      status <- system2(
        "python",
        c("scripts/p11_diagnostic_probes.py", "--config", p11_g_contract),
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
