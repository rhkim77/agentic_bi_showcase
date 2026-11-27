locals {
  required_apis = [
    "bigquery.googleapis.com",
    "geminidataanalytics.googleapis.com",
    "aiplatform.googleapis.com",
    "dataplex.googleapis.com",
    "cloudtrace.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ]

  resolved_image = (
    var.container_image != ""
    ? var.container_image
    : "${var.data_location}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/cymbal-agentic-bi-showcase:latest"
  )
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.data_location
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "Cloud Demo Engineering container images"
  depends_on    = [google_project_service.apis]
}

resource "google_bigquery_dataset" "cymbal_dataset" {
  project                    = var.project_id
  dataset_id                 = var.bq_dataset_id
  location                   = "US"
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.apis]
}

resource "google_service_account" "showcase_sa" {
  project      = var.project_id
  account_id   = "cymbal-bi-showcase-sa"
  display_name = "Cymbal Agentic BI Showcase Cloud Run SA"
  depends_on   = [google_project_service.apis]
}

# Project level: only what cannot be scoped lower (run BigQuery jobs, call Vertex AI).
resource "google_project_iam_member" "showcase_sa_roles" {
  for_each = toset([
    "roles/bigquery.user",
    "roles/aiplatform.user",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.showcase_sa.email}"
}

# Read access to the demo dataset only. Access to the seven Cymbal data agents is granted per data agent
# by scripts/grant_runtime_access.py once the provisioning scripts have created them.
resource "google_bigquery_dataset_iam_member" "showcase_sa_dataset_viewer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.cymbal_dataset.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.showcase_sa.email}"
}

resource "google_cloud_run_v2_service" "showcase" {
  project             = var.project_id
  name                = "cymbal-agentic-bi-showcase"
  location            = var.data_location
  ingress             = var.ingress
  deletion_protection = false

  template {
    service_account  = google_service_account.showcase_sa.email
    timeout          = "600s"
    session_affinity = true

    scaling {
      min_instance_count = 1
      max_instance_count = 5
    }

    containers {
      image = local.resolved_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "BQ_DATASET_ID"
        value = var.bq_dataset_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.data_location
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.images,
    google_project_iam_member.showcase_sa_roles,
    google_bigquery_dataset_iam_member.showcase_sa_dataset_viewer,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.showcase.location
  name     = google_cloud_run_v2_service.showcase.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "caller_invoker" {
  count    = (!var.allow_unauthenticated && var.gcp_account_name != "") ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.showcase.location
  name     = google_cloud_run_v2_service.showcase.name
  role     = "roles/run.invoker"
  member   = "user:${var.gcp_account_name}"
}
