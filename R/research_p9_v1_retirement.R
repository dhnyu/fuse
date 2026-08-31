# P9 v1 control-plane retirement. Historical readers remain available.
p9_v1_retired_stop <- function(interface) {
  stop(
    paste0(
      "P9_V1_EXECUTION_RETIRED: ", interface,
      ": P9 v1 is historical/read-only; execution is retired; ",
      "use a canonical p9accv2 acceptance through resolve_accepted_checkpoint()."
    ),
    call. = FALSE
  )
}
