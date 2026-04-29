resource "google_secret_manager_secret" "runtime" {
  for_each = var.manage_runtime_secrets ? var.runtime_secret_ids : []

  secret_id = each.value

  replication {
    auto {}
  }

  labels = {
    app        = "engineer-cafe-navigator"
    managed_by = "terraform"
    scope      = "runtime"
  }
}
