# Read-only recovery for metadata lost from the targets store. Accepted files are
# validated in place; this module never publishes or modifies scientific data.

metadata_recovery_sha256 <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

metadata_recovery_values <- function(value) {
  if (is.list(value)) return(unlist(lapply(value, metadata_recovery_values), use.names = FALSE))
  as.character(value)
}

metadata_recovery_lookup <- function(value, dotted_path) {
  parts <- strsplit(dotted_path, ".", fixed = TRUE)[[1L]]
  for (index in seq_along(parts)) {
    remainder <- paste(parts[index:length(parts)], collapse = ".")
    if (is.list(value) && !is.null(value[[remainder]])) return(value[[remainder]])
    part <- parts[[index]]
    if (!is.list(value) || is.null(value[[part]])) return(NULL)
    value <- value[[part]]
  }
  value
}

metadata_recovery_specs <- function() {
  list(
    prototype_dataloader_smoke = list(
      id = "pdl_5eb0ccb9951d1015d6d64649", manifest = "prototype_dataloader_smoke.json",
      manifest_sha256 = "c7b1ee51afcfb6268e1c633b5e6129647026f4683798b419d423ac3aac80b3d2",
      status = "READY", id_field = "smoke_id",
      files = c(prototype_dataloader_smoke.json = "c7b1ee51afcfb6268e1c633b5e6129647026f4683798b419d423ac3aac80b3d2",
                prototype_dataloader_smoke.jsonl = "74b05fcf5a0dd486b3914e7e97b6615a71dc54b7353e65ad20faa9573d23f846"),
      parents = c("ptd_bcb9e6a1061ff7ca9c716b20"),
      hashes = c("contract.dataloader_config_sha256" = "config/dataloader_smoke.yml",
                 "contract.dataset_implementation_sha256" = "python/prototype_dataloader.py",
                 "contract.requirements_sha256" = "python/requirements-dataloader.txt",
                 "contract.result_schema_sha256" = "config/schemas/prototype_dataloader_smoke.schema.json",
                 "contract.smoke_implementation_sha256" = "python/run_prototype_dataloader_smoke.py",
                 "contract.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_scientific_geometry_roundtrip = list(
      id = "pgr_77294c825bf26bf6fce721c3", manifest = "scientific_geometry_roundtrip_manifest.json",
      manifest_sha256 = "f8d422ccb659b95c1a4dec6af941acf1d1211956668d6a2760afef48a585a60b",
      status = "PASS", id_field = "gate_id",
      files = c(scientific_geometry_roundtrip_manifest.json = "f8d422ccb659b95c1a4dec6af941acf1d1211956668d6a2760afef48a585a60b",
                scientific_geometry_roundtrip_scenes.parquet = "112ca20ed9945481963c2e8dca1f9ae3721e97e9af452427c121a2c7f4c3d8d8"),
      parents = c("ptd_bcb9e6a1061ff7ca9c716b20", "pdl_5eb0ccb9951d1015d6d64649"),
      hashes = c("scientific_identity.implementation_sha256" = "python/prototype_augmentation.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-augmentation.txt",
                 "scientific_identity.runner_sha256" = "python/run_scientific_geometry_roundtrip.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_scientific_geometry_roundtrip.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_encoder_smoke = list(
      id = "pea_1c66760dbc1e6c0a8d71cb91", manifest = "prototype_encoder_manifest.json",
      manifest_sha256 = "612dcaaab4f1abe75b933e09a08818d8abca233c943b7da0f89f3476e3a680ff",
      status = "PASS", id_field = "encoder_acceptance_id",
      files = c(prototype_encoder_manifest.json = "612dcaaab4f1abe75b933e09a08818d8abca233c943b7da0f89f3476e3a680ff",
                prototype_encoder_parameters.parquet = "c2a9f586fc6bfa6d717d799a2b183043a1a9535c5b465abc20f4bafabf5e206b",
                prototype_encoder_qc.json = "b1965e9da5e56bc12bd7bcc83e85778cea1d99eb71b5e0846d8f6f4fc3bd605b",
                prototype_encoder_shapes.parquet = "7eeb9834199c396e6151c79081e2452c3c9cb414fa8243a603dda673c99b4fa9",
                prototype_encoder_smoke.jsonl = "931e85df7f826eb13cf17a4b09941ead81b357f3c37e6b52a29b70f25b6fe3eb"),
      parents = c("ptd_bcb9e6a1061ff7ca9c716b20", "pdl_5eb0ccb9951d1015d6d64649"),
      hashes = c("scientific_identity.model_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.model_implementation_sha256" = "python/prototype_encoder.py",
                 "scientific_identity.launcher_sha256" = "python/run_prototype_encoder_smoke.py",
                 "scientific_identity.smoke_implementation_sha256" = "python/prototype_encoder_smoke_impl.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-encoder.txt",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_encoder_smoke.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_augmentation_benchmark = list(
      id = "paa_5d2b1f56119e8d5f5050a75d", manifest = "prototype_augmentation_manifest.json",
      manifest_sha256 = "2ca73683fffe2eae173b70b3f256b8e9df049328895f8d5a4a437192e2b21ffb",
      status = "PASS", id_field = "augmentation_acceptance_id",
      files = c(prototype_augmentation_benchmark.jsonl = "56319e507710fea92f379185323e7dbaf80b11ef0891041a6976b9ca0d1ca456",
                prototype_augmentation_manifest.json = "2ca73683fffe2eae173b70b3f256b8e9df049328895f8d5a4a437192e2b21ffb",
                prototype_augmentation_qc.json = "d56f68d9d1453d41ba9a41655fe5ba0278b21c76661f5173ca55e0b4d8dc656b",
                prototype_augmentation_report.md = "1734a4d46c241c49c21bc29ee39a253cc08c392666b46cee566050d0641cbb89",
                prototype_augmentation_scene_results.parquet = "6bfe8cc9062abdb4b0264ccfdc52a1b3187e1ed08a935102c98a14a95b71905d"),
      parents = c("ptd_bcb9e6a1061ff7ca9c716b20", "pdl_5eb0ccb9951d1015d6d64649"),
      hashes = c("scientific_identity.implementation_sha256" = "python/prototype_augmentation.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-augmentation.txt",
                 "scientific_identity.runner_sha256" = "python/run_prototype_augmentation_benchmark.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_augmentation_benchmark.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_joint_model_smoke = list(
      id = "pjm_6e64c022281a7f2648f78917", manifest = "prototype_joint_model_manifest.json",
      manifest_sha256 = "23aac3e233e7f50d752067d83585e8fe7bc6a25d61c752979168093bbacb6d95",
      status = "PASS", id_field = "joint_model_acceptance_id",
      files = c(prototype_joint_model_manifest.json = "23aac3e233e7f50d752067d83585e8fe7bc6a25d61c752979168093bbacb6d95",
                prototype_joint_model_parameters.parquet = "3751dbcd7e956243cbab3610f8b9b83d1ba169b79268e788d296a5083a8bf1e0",
                prototype_joint_model_qc.json = "48e7d788a49047cc42fd5c5f9684be7ff288930d445d39ec79e041c8ac4fe7ea",
                prototype_joint_model_smoke.jsonl = "2ff0bd879cbea98bbd7caadbd14d101337c84952873b05126c46e11297136f83"),
      parents = c("ptd_bcb9e6a1061ff7ca9c716b20", "pdl_5eb0ccb9951d1015d6d64649", "pea_1c66760dbc1e6c0a8d71cb91",
                  "paa_5d2b1f56119e8d5f5050a75d", "pgr_77294c825bf26bf6fce721c3"),
      hashes = c("scientific_identity.encoder_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.implementation_sha256" = "python/prototype_joint_model.py",
                 "scientific_identity.joint_config_sha256" = "config/joint_model.yml",
                 "scientific_identity.launcher_sha256" = "python/run_prototype_joint_model_smoke.py",
                 "scientific_identity.smoke_sha256" = "python/prototype_joint_model_smoke_impl.py",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_distributed_joint_model_smoke = list(
      id = "pjd_69c0bd35dac8add3280d72e2", manifest = "distributed_joint_model_manifest.json",
      manifest_sha256 = "f37756949c14c918f8b8c9c06c118e929cab22465eed95bffc708d88188fd7a5",
      status = "PASS", id_field = "distributed_joint_acceptance_id",
      files = c(distributed_joint_model_manifest.json = "f37756949c14c918f8b8c9c06c118e929cab22465eed95bffc708d88188fd7a5",
                distributed_joint_model_qc.json = "181d28ca96892b5b62ddea986afa06f7a50bb720f066af63f0e2259a059dc7e8"),
      parents = c("pjm_6e64c022281a7f2648f78917"),
      hashes = c("scientific_identity.config_sha256" = "config/distributed_training.yml",
                 "scientific_identity.encoder_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.joint_config_sha256" = "config/joint_model.yml",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml",
                 "scientific_identity.implementation_sha256.prototype_ddp_joint_model.py" = "python/prototype_ddp_joint_model.py",
                 "scientific_identity.implementation_sha256.prototype_ddp_joint_objective_smoke.py" = "python/prototype_ddp_joint_objective_smoke.py",
                 "scientific_identity.implementation_sha256.prototype_sparse_reconstruction_smoke.py" = "python/prototype_sparse_reconstruction_smoke.py",
                 "scientific_identity.implementation_sha256.run_prototype_ddp_joint_smoke.py" = "python/run_prototype_ddp_joint_smoke.py")
    ),
    prototype_training_acceptance = list(
      id = "pta_cf6bc4679a06305fb1185a8e", manifest = "prototype_training_acceptance_manifest.json",
      manifest_sha256 = "7668a45b5f2525e2929379084e18560b33a4b3d419e80df3e018f6746592fc83",
      status = "PASS", id_field = "training_acceptance_id",
      files = c(checkpoint_catalog.json = "efa1860313ca068089d7c6d66a32f3636b254d82f28daca3baa1c278fa8fd4c6",
                prototype_training_acceptance_manifest.json = "7668a45b5f2525e2929379084e18560b33a4b3d419e80df3e018f6746592fc83",
                publication_recovery_qc.json = "fda2ae572ca98161f05fb3741bd5aaa34bcadb4849f18e29e3255def67169097",
                run_completion.json = "c566fc902d5447b0c974618082ac9450b5ce1e56f8c85ca137d756ab96eaaf12",
                validation_history.json = "afca0e1f595799de1ec19e198b0dfd0e941b595b52c7b0e03c6ff8f16bbf36a9"),
      parents = c("ptp_3b100622bdb733351db6e458", "ptr_473911a4828ae5540a9d4eb9"),
      hashes = c("scientific_identity.recovery_implementation_sha256" = "python/recover_prototype_training_acceptance.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_training_acceptance.schema.json",
                 "scientific_identity.training_contract_sha256" = "config/prototype_training.yml",
                 "scientific_identity.training_implementation_sha256" = "python/run_prototype_training_ddp.py")
    ),
    prototype_model_validation = list(
      id = "pmv_1d5412a7b035635a4187fbf6", manifest = "prototype_model_validation_manifest.json",
      manifest_sha256 = "a0722a4c4e7864bbad779c9a81fba1421b38f12caea87b210f85c9deedd2f060",
      status = "PASS", id_field = "model_validation_id",
      files = c(prototype_augmented_source_rankings.parquet = "df871c211759b79e6f70b1d150d77a71a46d6a93bbb329a600f1ddf144fd7b2f",
                prototype_model_validation_manifest.json = "a0722a4c4e7864bbad779c9a81fba1421b38f12caea87b210f85c9deedd2f060",
                prototype_model_validation_qc.json = "3e201d4c7d508d37ef980de9c21987c93c857fb3986edc119be3a4fc4e90a4be",
                prototype_model_validation_report.md = "a68f3b0e0438cf4e9c5411b0ff2e1bd7f7583da24724a2335677405eeed1b83d",
                prototype_original_scene_embeddings.parquet = "8a5135f55e5f8724e01d7a584ebc2bcc3751eb9a6e4af85290b2ea1402122967",
                prototype_original_scene_rankings.parquet = "7ba3abd9355c11939578fa8731b5c483de1d678d10a2f72b8946c250d1f33c5d"),
      parents = c("pta_cf6bc4679a06305fb1185a8e", "ptd_cee61a525ca92f1b7951c40d", "paa_8d73a94e574dcdbc5c5106d2",
                  "ptp_3b100622bdb733351db6e458", "ptr_473911a4828ae5540a9d4eb9"),
      current_hashes = c("config/prototype_model_validation.yml" = "bbbb0b94b627a1231e2f9fd16384c20185993585e4f6bd85fbe2d1cc8b409699"),
      hashes = c("scientific_identity.augmentation_config_sha256" = "config/augmentation.yml",
                 "scientific_identity.encoder_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_model_validation.schema.json",
                 "scientific_identity.source_sha256" = "python/run_prototype_model_validation.py",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_model_acceptance = list(
      id = "pma_6282c9e9f9ebb9348484223a", manifest = "prototype_model_acceptance.json",
      manifest_sha256 = "08fcedc088f0730d4ed9ede6c0d029e1da7e1fad01b6b5e527c3a63110d9a26a",
      status = "PASS", id_field = "model_acceptance_id",
      files = c(prototype_model_acceptance.json = "08fcedc088f0730d4ed9ede6c0d029e1da7e1fad01b6b5e527c3a63110d9a26a",
                prototype_model_acceptance.md = "1210af848179f15902f68cc51812bc1d18e3db5117ed593e98836585c5afb7ee"),
      parents = c("pdl_4037d275d729c82ea9b19d97", "pea_5784252434798d9dfa05d796", "paa_8d73a94e574dcdbc5c5106d2",
                  "pta_cf6bc4679a06305fb1185a8e", "pmv_1d5412a7b035635a4187fbf6"),
      hashes = c("scientific_identity.config_sha256" = "config/prototype_model_acceptance.yml",
                 "scientific_identity.implementation_sha256" = "python/accept_prototype_model.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_model_acceptance.schema.json")
    )
  )
}

validate_metadata_recovery_bundle <- function(target_name, directory, spec = metadata_recovery_specs()[[target_name]]) {
  if (is.null(spec)) stop("Unknown metadata recovery target: ", target_name, call. = FALSE)
  directory <- normalizePath(directory, mustWork = TRUE)
  actual_names <- sort(basename(list.files(directory, full.names = TRUE, recursive = FALSE, include.dirs = FALSE)), method = "radix")
  expected_names <- sort(names(spec$files), method = "radix")
  if (!identical(actual_names, expected_names)) {
    stop("Immutable recovery file-set mismatch for ", target_name, "; missing=",
         paste(setdiff(expected_names, actual_names), collapse = ","), "; extra=",
         paste(setdiff(actual_names, expected_names), collapse = ","), call. = FALSE)
  }
  paths <- file.path(directory, names(spec$files))
  observed_sha <- vapply(paths, metadata_recovery_sha256, character(1L))
  if (!identical(unname(observed_sha), unname(spec$files))) {
    bad <- names(spec$files)[observed_sha != spec$files]
    stop("Immutable recovery checksum mismatch for ", target_name, ": ", paste(bad, collapse = ","), call. = FALSE)
  }
  manifest_path <- file.path(directory, spec$manifest)
  if (!identical(metadata_recovery_sha256(manifest_path), spec$manifest_sha256)) {
    stop("Immutable recovery manifest checksum mismatch for ", target_name, call. = FALSE)
  }
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  if (!identical(manifest$status, spec$status) || !identical(manifest[[spec$id_field]], spec$id)) {
    stop("Immutable recovery identity/status mismatch for ", target_name, call. = FALSE)
  }
  values <- metadata_recovery_values(manifest)
  missing_parents <- setdiff(spec$parents, values)
  if (length(missing_parents)) {
    stop("Immutable recovery foreign/missing parent for ", target_name, ": ", paste(missing_parents, collapse = ","), call. = FALSE)
  }
  for (field in names(spec$hashes)) {
    path <- spec$hashes[[field]]
    expected <- metadata_recovery_lookup(manifest, field)
    observed <- metadata_recovery_sha256(path)
    if (!identical(expected, observed)) {
      stop("Immutable recovery stale implementation/config/schema for ", target_name, ": ", field, call. = FALSE)
    }
  }
  for (field in names(spec$runtime_only_hashes)) {
    transition <- spec$runtime_only_hashes[[field]]
    accepted <- metadata_recovery_lookup(manifest, field)
    if (!identical(accepted, transition$accepted) ||
        !identical(metadata_recovery_sha256(transition$path), transition$current)) {
      stop("Immutable recovery unapproved runtime-only hash transition for ", target_name, ": ", field, call. = FALSE)
    }
  }
  for (path in names(spec$current_hashes)) {
    if (!identical(metadata_recovery_sha256(path), unname(spec$current_hashes[[path]]))) {
      stop("Immutable recovery stale implementation/config/schema for ", target_name, ": ", path, call. = FALSE)
    }
  }
  normalizePath(paths, mustWork = TRUE)
}

recover_file_target_metadata <- function(target_name, directory, fallback,
                                         spec = metadata_recovery_specs()[[target_name]]) {
  recovered <- tryCatch(
    validate_metadata_recovery_bundle(target_name, directory, spec = spec),
    error = function(error) {
      if (identical(Sys.getenv("FUSE_METADATA_RECOVERY_ONLY"), "1")) {
        stop("Metadata recovery-only fast path rejected for ", target_name, ": ", conditionMessage(error), call. = FALSE)
      }
      message("Metadata fast path rejected for ", target_name, ": ", conditionMessage(error), "; running target normally")
      NULL
    }
  )
  if (!is.null(recovered)) {
    message("Metadata fast path verified: ", target_name)
    return(recovered)
  }
  fallback
}

metadata_recovery_dataset_root <- function(prototype_training_dataset_acceptance) {
  files <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  manifest <- files[basename(files) == "accepted_training_dataset_manifest.json"]
  if (length(manifest) != 1L) stop("I16 accepted manifest unavailable for metadata recovery", call. = FALSE)
  dirname(manifest)
}

recover_training_plan_metadata <- function(training_plan_contract_files, fallback) {
  files <- normalizePath(training_plan_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  config <- yaml::read_yaml(by_name[["training_plan.yml"]])
  directory <- file.path(config$output$root, "ptp_b26daa03f4fdc6717d53cc33")
  expected <- c(`run-spec.json` = "3eb0b456c65b895b3aa3693c9c7110215ab47ba0c667a61613e7424f62c8d4e4",
                prototype_training_plan_qc.json = "75bc77bd47fc89b90662b8aefa5f8b415759c972b8db2b71d2fd42117cb28a44",
                prototype_training_plan_manifest.json = "de8d5993525fd85d8abf70c5a400ebcf3c9a24ceeb5eb838d83ea17155063848")
  recovered <- tryCatch({
    actual <- sort(basename(list.files(directory, full.names = TRUE, recursive = FALSE)), method = "radix")
    if (!identical(actual, sort(names(expected), method = "radix"))) stop("I20 file-set mismatch")
    paths <- file.path(directory, names(expected))
    sha <- vapply(paths, metadata_recovery_sha256, character(1L))
    if (!identical(unname(sha), unname(expected))) stop("I20 checksum mismatch")
    manifest <- jsonlite::read_json(file.path(directory, "prototype_training_plan_manifest.json"), simplifyVector = FALSE)
    run <- jsonlite::read_json(file.path(directory, "run-spec.json"), simplifyVector = FALSE)
    if (!identical(manifest$status, "PASS") || !identical(manifest$plan_id, "ptp_b26daa03f4fdc6717d53cc33") ||
        !identical(run$plan_id, manifest$plan_id) || !identical(run$run_id, "ptr_50be4e6c09161b4c3aae940e")) {
      stop("I20 identity/status mismatch")
    }
    if (!identical(manifest$scientific_identity$implementation_sha256, metadata_recovery_sha256("R/research_training_plan.R")) ||
        !identical(manifest$scientific_identity$schema_sha256, metadata_recovery_sha256("config/schemas/prototype_training_plan.schema.json"))) {
      stop("I20 stale implementation/schema")
    }
    model <- yaml::read_yaml(by_name[["model_architecture.yml"]])
    joint <- yaml::read_yaml(by_name[["joint_model.yml"]])
    augmentation_config <- yaml::read_yaml(by_name[["augmentation.yml"]])
    scoped <- list(
      model = model[c("dimensions", "position", "geometry", "architecture")],
      joint = joint[c("numerical_policy", "modality_masking", "decoders", "loss", "contrastive")],
      augmentation = augmentation_config[c("rng", "entity_removal", "geometry", "attributes", "categorical", "raster", "relations")],
      training = config[c("runs", "data", "optimization", "validation", "resume")],
      execution = config$execution[c(
        "distributed_strategy", "distributed_backend", "world_size", "workers_per_rank",
        "rank_logical_batch_scenes", "persistent_workers", "pin_memory", "prefetch_factor",
        "native_threads_per_worker", "process_start_method"
      )]
    )
    scoped_sha <- lapply(scoped, digest::digest, algo = "sha256", serialize = TRUE)
    if (!identical(manifest$scientific_identity$scientific_hashes, scoped_sha)) stop("I20 stale scientific config")
    current_config_sha <- c(
      model_architecture.yml = "0ad34e2d14094ecb9aef86804328f461e9955e08f8eac2873587eb9987a11807",
      joint_model.yml = "56b7d83cffe309f61d20304485412035913324385519bcc6327f10ff781da367",
      augmentation.yml = "38fc6ec2df35b1de481048daf8606ff3ab37237f04c511fc053654d83f21b75a",
      training_plan.yml = "ef1fabe78d20b1a9783c65ae731cdcd6ae3b8396f8abfc613ad7ebe69bcf70a6"
    )
    for (name in names(current_config_sha)) {
      if (!identical(metadata_recovery_sha256(by_name[[name]]), unname(current_config_sha[[name]]))) {
        stop("I20 stale config: ", name)
      }
    }
    required <- c("ptd_8b3359690ea2d0bef52d63e3", "pdl_361072e3519a91d0aefc9bb9", "pgr_4fcebb65e897c22dcc202950",
                  "pea_dba8976447199f1b67ae5216", "paa_f49a5e16e0855b7bad5e4e60", "pjm_2c43bef0ecb99c26eba58bbf",
                  "pjd_394f70f85445591ad7ad930c")
    if (length(setdiff(required, metadata_recovery_values(manifest)))) stop("I20 parent mismatch")
    message("Metadata fast path verified: prototype_training_plan")
    list(list(run_id = run$run_id, plan_id = run$plan_id,
              .path = normalizePath(file.path(directory, "run-spec.json"), mustWork = TRUE),
              files = unname(normalizePath(paths, mustWork = TRUE))))
  }, error = function(error) {
    if (identical(Sys.getenv("FUSE_METADATA_RECOVERY_ONLY"), "1")) {
      stop("Metadata recovery-only fast path rejected for prototype_training_plan: ", conditionMessage(error), call. = FALSE)
    }
    message("Metadata fast path rejected for prototype_training_plan: ", conditionMessage(error), "; running target normally")
    NULL
  })
  if (!is.null(recovered)) return(recovered)
  fallback
}
