output "cloud_run_service_url" {
  description = "Deployed Cymbal Agentic BI Showcase Cloud Run URL"
  value       = google_cloud_run_v2_service.showcase.uri
}

output "bigquery_dataset" {
  description = "BigQuery Dataset backing the 3 Domain CAA Data Agents"
  value       = "${var.project_id}.${google_bigquery_dataset.cymbal_dataset.dataset_id}"
}
