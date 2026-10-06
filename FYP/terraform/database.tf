# Database: a small PostgreSQL instance on RDS. PostGIS is enabled by the app's schema.sql
# (CREATE EXTENSION postgis), which the master user is allowed to run.

# Generated password; it never appears in the code or on GitHub.
# Letters and digits only, so it is safe to put inside a connection URL.
resource "random_password" "db" {
  length  = 32
  special = false
}

# Tells RDS which subnets it may use: the two private ones
resource "aws_db_subnet_group" "main" {
  name       = "copc-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier     = "copc-db"
  engine         = "postgres"
  engine_version = "16" # same major version as the local docker-compose database
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "copc_db"
  username = "copc_admin"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  # Demo settings so "terraform destroy" is quick and leaves nothing behind that costs money.
  # A production database would keep backups and take a final snapshot.
  backup_retention_period = 0
  skip_final_snapshot     = true
  apply_immediately       = true
}

# The full connection string the app expects in DATABASE_URL, stored encrypted.
# The API container will read it from here at startup.
resource "aws_ssm_parameter" "database_url" {
  name  = "/copc/database-url"
  type  = "SecureString"
  value = "postgresql://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.endpoint}/${aws_db_instance.main.db_name}"
}

output "db_endpoint" {
  value = aws_db_instance.main.endpoint
}
