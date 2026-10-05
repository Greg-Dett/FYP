    terraform {
     required_version = ">= 1.5"

     required_providers {
       aws = {
         source  = "hashicorp/aws"
         version = "~> 6.0"
       }
     }
   }

   provider "aws" {
     region = "eu-west-1"

     default_tags {
       tags = {
         Project   = "copc-query"
         ManagedBy = "terraform"
       }
     }
   }

   data "aws_caller_identity" "current" {}

   resource "aws_s3_bucket" "copc_data" {
     bucket        = "copc-data-${data.aws_caller_identity.current.account_id}"
     force_destroy = true
   }

   resource "aws_s3_bucket_public_access_block" "copc_data" {
     bucket = aws_s3_bucket.copc_data.id

     block_public_acls       = true
     block_public_policy     = true
     ignore_public_acls      = true
     restrict_public_buckets = true
   }

   output "copc_bucket_name" {
     value = aws_s3_bucket.copc_data.bucket
   }
