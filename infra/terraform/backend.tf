terraform {
  backend "gcs" {
    bucket = "aipartner-426616-tfstate"
    prefix = "engineer-cafe-backend/observability"
  }
}

