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

variable "artifact_repo" {
  type        = string
  description = "Artifact Registry Docker repository ID in var.project_id."
  default     = "demo-eng-images"
}

variable "container_image" {
  type        = string
  description = "Optional full container image URI. When empty, defaults to <data_location>-docker.pkg.dev/<project_id>/<artifact_repo>/cymbal-agentic-bi-showcase:latest."
  default     = ""
}

variable "ingress" {
  type        = string
  description = "Cloud Run ingress setting. Use INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER in orgs that enforce constraints/run.allowedIngress."
  default     = "INGRESS_TRAFFIC_ALL"

  validation {
    condition = contains([
      "INGRESS_TRAFFIC_ALL",
      "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
      "INGRESS_TRAFFIC_INTERNAL_ONLY",
    ], var.ingress)
    error_message = "ingress must be INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER, or INGRESS_TRAFFIC_INTERNAL_ONLY."
  }
}

variable "allow_unauthenticated" {
  type        = bool
  description = "Grant roles/run.invoker to allUsers. Keep false in Domain Restricted Sharing orgs and access via 'gcloud run services proxy' or authenticated IAM."
  default     = false
}
