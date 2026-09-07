list_p11_living_population_rematerialization <- list(
  targets::tar_target(
    s11_living_sources,
    p11_living_source_files(),
    format = "file"
  ),
  targets::tar_target(
    s11_living_dataset_cache,
    p11_output_paths(p11_execute_living_partial_support_rematerialization(
      p11_source_file(s11_living_sources, "p11_downstream_preprocessing_v2.yml")
    )),
    format = "file"
  )
)
