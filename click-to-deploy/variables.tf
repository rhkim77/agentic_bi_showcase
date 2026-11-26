variable "project_id" {
  type        = string
  description = "The GCP Project ID where the demo resources will be deployed."
}

variable "project_name" {
  type        = string
  description = "The human-readable GCP Project Name."
  default     = ""
}

variable "project_number" {
  type        = string
  description = "The numeric GCP Project Number."
  default     = ""
}

variable "org_id" {
  type        = string
  description = "The GCP Organization ID."
  default     = ""
}

variable "gcp_account_name" {
  type        = string
  description = "The user account email triggering the Click-to-Deploy run."
  default     = ""
}

variable "deployment_service_account_name" {
  type        = string
  description = "The service account used by the Demo Automation Platform to execute Terraform."
  default     = ""
}

variable "data_location" {
  type        = string
  description = "Default region for Cloud Run and Artifact Registry resources."
  default     = "us-central1"
}

variable "secret_stored_project" {
  type        = string
  description = "The GCP project ID where demo secrets are stored."
  default     = ""
}

variable "bq_dataset_id" {
  type        = string
  description = "BigQuery Dataset ID for Cymbal Global Commerce analytics."
  default     = "cymbal_enterprise_dw"
}

variable "container_image" {
  type        = string
  description = "Pre-built Artifact Registry container image URI."
  default     = "us-central1-docker.pkg.dev/ryan-sandbox-agent/demo-eng-images/cymbal-agentic-bi-showcase:latest"
}
