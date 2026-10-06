# Network: one VPC with two public subnets (for the API) and two private subnets (for the database).
# There is no NAT gateway, which keeps the cost down: the API will run in the public subnets,
# and the database has no route to or from the internet at all.

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "copc-vpc" }
}

# The VPC's door to the internet
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "copc-igw" }
}

# Public subnets, one in each of two availability zones: 10.0.0.0/24 and 10.0.1.0/24
resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "copc-public-${count.index + 1}" }
}

# Private subnets for the database: 10.0.10.0/24 and 10.0.11.0/24.
# RDS requires subnets in at least two availability zones.
resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "copc-private-${count.index + 1}" }
}

# Sends internet-bound traffic from the public subnets through the internet gateway.
# The private subnets are not attached to it, which is what makes them private.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "copc-public" }
}

resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Security groups are firewalls attached to individual resources.

# For the API containers. Inbound rules are added when the API is deployed.
resource "aws_security_group" "api" {
  name        = "copc-api"
  description = "API containers"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "copc-api" }
}

# The API may call out anywhere (S3, the database, pulling its image)
resource "aws_vpc_security_group_egress_rule" "api_all_out" {
  security_group_id = aws_security_group.api.id
  description       = "All outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# For the database
resource "aws_security_group" "db" {
  name        = "copc-db"
  description = "PostgreSQL database"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "copc-db" }
}

# The only way in to the database: PostgreSQL traffic from the API's security group
resource "aws_vpc_security_group_ingress_rule" "db_from_api" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL from the API"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.api.id
}
