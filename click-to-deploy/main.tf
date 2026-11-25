locals {
  required_apis = [
    "bigquery.googleapis.com",
    "geminidataanalytics.googleapis.com",
    "aiplatform.googleapis.com",
    "dataplex.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "cymbal_dataset" {
  dataset_id                 = var.bq_dataset_id
  location                   = "US"
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.apis]
}

resource "google_service_account" "showcase_sa" {
  account_id   = "cymbal-bi-showcase-sa"
  display_name = "Cymbal Agentic BI Showcase Cloud Run SA"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "showcase_sa_roles" {
  for_each = toset([
    "roles/bigquery.user",
    "roles/bigquery.dataViewer",
    "roles/aiplatform.user",
    "roles/geminidataanalytics.dataAgentUser",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.showcase_sa.email}"
}

resource "google_cloud_run_v2_service" "showcase" {
  name     = "cymbal-agentic-bi-showcase"
  location = var.data_location
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.showcase_sa.email
    timeout         = "180s"
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
    containers {
      image = var.container_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
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
  depends_on = [google_project_iam_member.showcase_sa_roles]
}
