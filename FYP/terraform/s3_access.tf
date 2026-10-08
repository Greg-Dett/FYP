# Lets the API read COPC files from the bucket while the bucket stays private.
# The app reads files over plain HTTPS using range requests, so access is granted by
# network path, not by credentials: only requests that arrive through this VPC's
# S3 endpoint are allowed. From anywhere else the same URL returns 403.

data "aws_region" "current" {}

# Gateway endpoint: a private route from the public subnets to S3. It is free.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]

  tags = { Name = "copc-s3" }
}

data "aws_iam_policy_document" "copc_data_read" {
  statement {
    sid       = "ReadOnlyThroughVpcEndpoint"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.copc_data.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpce"
      values   = [aws_vpc_endpoint.s3.id]
    }
  }
}

resource "aws_s3_bucket_policy" "copc_data" {
  bucket = aws_s3_bucket.copc_data.id
  policy = data.aws_iam_policy_document.copc_data_read.json

  depends_on = [aws_s3_bucket_public_access_block.copc_data]
}

# The address to register files under, e.g. <this>/T_315000_233500.copc
output "copc_bucket_url" {
  value = "https://${aws_s3_bucket.copc_data.bucket_regional_domain_name}"
}
