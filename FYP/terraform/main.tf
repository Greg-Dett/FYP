# Infrastructure for the COPC query API.
# Run from this folder:  terraform init  ->  terraform plan  ->  terraform apply

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # Used to generate the database password
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1" # Ireland

  # Every resource gets these tags, so project costs are easy to find in the billing console
  default_tags {
    tags = {
      Project   = "copc-query"
      ManagedBy = "terraform"
    }
  }
}

# Looks up the account ID; bucket names must be unique across all of AWS,
# so the ID is added to the name
data "aws_caller_identity" "current" {}

# Holds the COPC files that the API reads with HTTP range requests
resource "aws_s3_bucket" "copc_data" {
  bucket = "copc-data-${data.aws_caller_identity.current.account_id}"

  # Lets "terraform destroy" delete the bucket even when it contains files.
  # Fine here because the tiles can be re-uploaded; do not use for irreplaceable data.
  force_destroy = true
}

# Keep the bucket private: nothing in it can be made public by accident
resource "aws_s3_bucket_public_access_block" "copc_data" {
  bucket = aws_s3_bucket.copc_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Printed after "terraform apply"
output "copc_bucket_name" {
  value = aws_s3_bucket.copc_data.bucket
}
