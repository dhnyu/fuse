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
      id = "pdl_4037d275d729c82ea9b19d97", manifest = "prototype_dataloader_smoke.json",
      manifest_sha256 = "f9ecea81f42f3450a77993330f1cf4c3242399c0efc677b5ee137407a933195b",
      status = "READY", id_field = "smoke_id",
      files = c(prototype_dataloader_smoke.json = "f9ecea81f42f3450a77993330f1cf4c3242399c0efc677b5ee137407a933195b",
                prototype_dataloader_smoke.jsonl = "f22280ea19d08622f019394d5436dfc27b61b016980cf6412cc770b47aac36ef"),
      parents = c("ptd_cee61a525ca92f1b7951c40d"),
      hashes = c("contract.dataloader_config_sha256" = "config/dataloader_smoke.yml",
                 "contract.dataset_implementation_sha256" = "python/prototype_dataloader.py",
                 "contract.requirements_sha256" = "python/requirements-dataloader.txt",
                 "contract.result_schema_sha256" = "config/schemas/prototype_dataloader_smoke.schema.json",
                 "contract.smoke_implementation_sha256" = "python/run_prototype_dataloader_smoke.py",
                 "contract.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_scientific_geometry_roundtrip = list(
      id = "pgr_fb3209bda9fb0fa9a0e15bd1", manifest = "scientific_geometry_roundtrip_manifest.json",
      manifest_sha256 = "724fb7dba6c067108b40ed72f130e6c2ae8fd554d82d80663001625a2bcd2351",
      status = "PASS", id_field = "gate_id",
      files = c(scientific_geometry_roundtrip_manifest.json = "724fb7dba6c067108b40ed72f130e6c2ae8fd554d82d80663001625a2bcd2351",
                scientific_geometry_roundtrip_scenes.parquet = "a2e69a08f05e4bddfca2810ebf41f9ae21c95311a74833ddffc7a4f8194fd65f"),
      parents = c("ptd_cee61a525ca92f1b7951c40d", "pdl_4037d275d729c82ea9b19d97"),
      hashes = c("scientific_identity.implementation_sha256" = "python/prototype_augmentation.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-augmentation.txt",
                 "scientific_identity.runner_sha256" = "python/run_scientific_geometry_roundtrip.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_scientific_geometry_roundtrip.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_encoder_smoke = list(
      id = "pea_5784252434798d9dfa05d796", manifest = "prototype_encoder_manifest.json",
      manifest_sha256 = "40a5bb613df60638b237f87b41b8bac27a3f9a48ec3f922be80086449382c7f1",
      status = "PASS", id_field = "encoder_acceptance_id",
      files = c(prototype_encoder_manifest.json = "40a5bb613df60638b237f87b41b8bac27a3f9a48ec3f922be80086449382c7f1",
                prototype_encoder_parameters.parquet = "5f5bd5968ef4f4de26b452043a7aa113716b600e6179dad7c8c2a19f580221d2",
                prototype_encoder_qc.json = "802e15cd6e337e4ac68ebd565cece874d792f0f3079e04a42298c81bd72261a0",
                prototype_encoder_shapes.parquet = "4414fcac83aba32402b2b6cd685ca08bf4eefd33fb2bd9771f42acfb55c19604",
                prototype_encoder_smoke.jsonl = "63d4c1811249d3885e584f873e526e51eeff3f11d9031f7a59e6a8d674f72ddc"),
      parents = c("ptd_cee61a525ca92f1b7951c40d", "pdl_4037d275d729c82ea9b19d97"),
      hashes = c("scientific_identity.model_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.model_implementation_sha256" = "python/prototype_encoder.py",
                 "scientific_identity.launcher_sha256" = "python/run_prototype_encoder_smoke.py",
                 "scientific_identity.smoke_implementation_sha256" = "python/prototype_encoder_smoke_impl.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-encoder.txt",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_encoder_smoke.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_augmentation_benchmark = list(
      id = "paa_8d73a94e574dcdbc5c5106d2", manifest = "prototype_augmentation_manifest.json",
      manifest_sha256 = "cd81f7921625a3cec4d1f2954c02869431a26cc75c24d7d7601029d3b86fe836",
      status = "PASS", id_field = "augmentation_acceptance_id",
      files = c(prototype_augmentation_benchmark.jsonl = "aceb59ca97ca30c5fa275b185199d7ff0ebb62d712e0b55a04314e25c8ff67fc",
                prototype_augmentation_manifest.json = "cd81f7921625a3cec4d1f2954c02869431a26cc75c24d7d7601029d3b86fe836",
                prototype_augmentation_qc.json = "d97ff5c2e9814679d50f2120d03a7993a1cbd626271e04a1829b3fbf228c901a",
                prototype_augmentation_report.md = "ed60373ee2db379bb759e983410204b7234e021e8cb1ae2b30d2a85201610625",
                prototype_augmentation_scene_results.parquet = "4cf3f8d370c5b97acc98de98ebf86b1c1de96e2dba20b7845eca1de8ea038e90"),
      parents = c("ptd_cee61a525ca92f1b7951c40d", "pdl_4037d275d729c82ea9b19d97"),
      hashes = c("scientific_identity.implementation_sha256" = "python/prototype_augmentation.py",
                 "scientific_identity.requirements_sha256" = "python/requirements-augmentation.txt",
                 "scientific_identity.runner_sha256" = "python/run_prototype_augmentation_benchmark.py",
                 "scientific_identity.schema_sha256" = "config/schemas/prototype_augmentation_benchmark.schema.json",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_joint_model_smoke = list(
      id = "pjm_056c0d32b223808fd8dabc75", manifest = "prototype_joint_model_manifest.json",
      manifest_sha256 = "a1ab0fd3cdf50836495dbc897b787183c17ec2895bde19b37147f6f31fc9d27a",
      status = "PASS", id_field = "joint_model_acceptance_id",
      files = c(prototype_joint_model_manifest.json = "a1ab0fd3cdf50836495dbc897b787183c17ec2895bde19b37147f6f31fc9d27a",
                prototype_joint_model_parameters.parquet = "c8bf126a9e777fe6cbc3e78ff54295c07f299b42cf526419711ec4e516c4868d",
                prototype_joint_model_qc.json = "2134e01ef2186d332847407216021f52363949df8f8c43409e5364a30fb60525",
                prototype_joint_model_smoke.jsonl = "56b6b7c8b0727da34c030f3651c1c9a95069a944b14609232429c3551b05755a"),
      parents = c("ptd_cee61a525ca92f1b7951c40d", "pdl_4037d275d729c82ea9b19d97", "pea_5784252434798d9dfa05d796",
                  "paa_8d73a94e574dcdbc5c5106d2", "pgr_fb3209bda9fb0fa9a0e15bd1"),
      hashes = c("scientific_identity.encoder_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.implementation_sha256" = "python/prototype_joint_model.py",
                 "scientific_identity.joint_config_sha256" = "config/joint_model.yml",
                 "scientific_identity.launcher_sha256" = "python/run_prototype_joint_model_smoke.py",
                 "scientific_identity.smoke_sha256" = "python/prototype_joint_model_smoke_impl.py",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml")
    ),
    prototype_distributed_joint_model_smoke = list(
      id = "pjd_13aff4a58d3d6022ee2dd62f", manifest = "distributed_joint_model_manifest.json",
      manifest_sha256 = "e911d44b88f79f86dfe6026d80f94b0fb03e6b83b175361183197e001da38696",
      status = "PASS", id_field = "distributed_joint_acceptance_id",
      files = c(distributed_joint_model_manifest.json = "e911d44b88f79f86dfe6026d80f94b0fb03e6b83b175361183197e001da38696",
                distributed_joint_model_qc.json = "611410c5f1898e03e7966bd08e97910b44a791569d72d49e025d81bc537ba1a6"),
      parents = c("pjm_056c0d32b223808fd8dabc75"),
      hashes = c("scientific_identity.config_sha256" = "config/distributed_training.yml",
                 "scientific_identity.encoder_config_sha256" = "config/model_architecture.yml",
                 "scientific_identity.joint_config_sha256" = "config/joint_model.yml",
                 "scientific_identity.tensor_contract_sha256" = "config/serialization_shard.yml",
                 "scientific_identity.implementation_sha256.prototype_ddp_joint_model.py" = "python/prototype_ddp_joint_model.py",
                 "scientific_identity.implementation_sha256.prototype_ddp_joint_objective_smoke.py" = "python/prototype_ddp_joint_objective_smoke.py",
                 "scientific_identity.implementation_sha256.prototype_ddp_optimizer_smoke.py" = "python/prototype_ddp_optimizer_smoke.py",
                 "scientific_identity.implementation_sha256.run_prototype_ddp_joint_smoke.py" = "python/run_prototype_ddp_joint_smoke.py",
                 "scientific_identity.implementation_sha256.run_prototype_training_ddp.py" = "python/run_prototype_training_ddp.py")
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
  for (path in names(spec$current_hashes)) {
    if (!identical(metadata_recovery_sha256(path), unname(spec$current_hashes[[path]]))) {
      stop("Immutable recovery stale implementation/config/schema for ", target_name, ": ", path, call. = FALSE)
    }
  }
  normalizePath(paths, mustWork = TRUE)
}

recover_file_target_metadata <- function(target_name, directory, fallback) {
  recovered <- tryCatch(
    validate_metadata_recovery_bundle(target_name, directory),
    error = function(error) {
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
  directory <- file.path(config$output$root, "ptp_3b100622bdb733351db6e458")
  expected <- c(prototype_training_plan_manifest.json = "8cec8d13aa437661e83e494ad6b208154a494ff024a580aa8086b8f76ad78674",
                prototype_training_plan_qc.json = "153b52aae5712ddb48b92e309f1f45344c64331c7d51d8fda48cc9d4b3cb1c93",
                `run-spec.json` = "af9c763c22de66d27a970deab17bd5589fa71518451fb3da66106f7cb8ef4f05")
  recovered <- tryCatch({
    actual <- sort(basename(list.files(directory, full.names = TRUE, recursive = FALSE)), method = "radix")
    if (!identical(actual, sort(names(expected), method = "radix"))) stop("I20 file-set mismatch")
    paths <- file.path(directory, names(expected))
    sha <- vapply(paths, metadata_recovery_sha256, character(1L))
    if (!identical(unname(sha), unname(expected))) stop("I20 checksum mismatch")
    manifest <- jsonlite::read_json(file.path(directory, "prototype_training_plan_manifest.json"), simplifyVector = FALSE)
    run <- jsonlite::read_json(file.path(directory, "run-spec.json"), simplifyVector = FALSE)
    if (!identical(manifest$status, "PASS") || !identical(manifest$plan_id, "ptp_3b100622bdb733351db6e458") ||
        !identical(run$run_id, "ptr_473911a4828ae5540a9d4eb9")) stop("I20 identity/status mismatch")
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
      augmentation = manifest[c("rng", "entity_removal", "geometry", "attributes", "categorical", "raster", "relations")],
      training = config[c("runs", "data", "optimization", "validation", "resume")]
    )
    scoped_sha <- lapply(scoped, digest::digest, algo = "sha256", serialize = TRUE)
    if (!identical(manifest$scientific_identity$scientific_hashes, scoped_sha)) stop("I20 stale scientific config")
    current_config_sha <- c(
      model_architecture.yml = "2839657ca8eff2a80656b21d04de524d99feab8c4ddf0a768c5192f50b030659",
      joint_model.yml = "8b097846e3ea005f23d0ecc78e28623db56f28575a174ab472ac366ec8d52a16",
      augmentation.yml = "ede938387d23d9cda71943aea57bd3342d4303d152c25cbe81193cca70100d2f",
      training_plan.yml = "8b02acae7c7f2b794684004172cdb7bf284f2be39b4ccc0570817b86fceb3947"
    )
    for (name in names(current_config_sha)) {
      if (!identical(metadata_recovery_sha256(by_name[[name]]), unname(current_config_sha[[name]]))) {
        stop("I20 stale config: ", name)
      }
    }
    required <- c("ptd_cee61a525ca92f1b7951c40d", "pdl_4037d275d729c82ea9b19d97", "pgr_fb3209bda9fb0fa9a0e15bd1",
                  "pea_5784252434798d9dfa05d796", "paa_8d73a94e574dcdbc5c5106d2", "pjm_056c0d32b223808fd8dabc75",
                  "pjd_13aff4a58d3d6022ee2dd62f")
    if (length(setdiff(required, metadata_recovery_values(manifest)))) stop("I20 parent mismatch")
    message("Metadata fast path verified: prototype_training_plan")
    list(list(run_id = run$run_id, plan_id = run$plan_id,
              .path = normalizePath(file.path(directory, "run-spec.json"), mustWork = TRUE),
              files = normalizePath(paths, mustWork = TRUE)))
  }, error = function(error) {
    message("Metadata fast path rejected for prototype_training_plan: ", conditionMessage(error), "; running target normally")
    NULL
  })
  if (!is.null(recovered)) return(recovered)
  fallback
}
