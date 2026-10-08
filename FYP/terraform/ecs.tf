# Runs the API container on ECS Fargate: AWS runs the container, there is no server to manage.
# One task runs in the public subnets with a public IP. There is no load balancer, to keep costs down.

# Container output (the gunicorn log) goes here
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/copc-api"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "main" {
  name = "copc"
}

# Execution role: what ECS itself may do to start the container
# (pull the image, write logs, read the database connection string)
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "copc-api-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Least privilege: this role can read one parameter, not every secret in the account
data "aws_iam_policy_document" "read_database_url" {
  statement {
    actions   = ["ssm:GetParameters"]
    resources = [aws_ssm_parameter.database_url.arn]
  }
}

resource "aws_iam_role_policy" "read_database_url" {
  name   = "read-database-url"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_database_url.json
}

# Task definition: which image to run and how
resource "aws_ecs_task_definition" "api" {
  family                   = "copc-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024 # 1 vCPU
  memory                   = 2048 # 2 GB, headroom for PDAL
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${aws_ecr_repository.api.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 5000
      protocol      = "tcp"
    }]

    # Injected as an environment variable at startup; the value never appears in this file
    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = aws_ssm_parameter.database_url.arn
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

# Service: keeps one copy of the task running and restarts it if it stops
resource "aws_ecs_service" "api" {
  name            = "copc-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = true # needed to pull the image, since there is no NAT gateway
  }

  # The role's permissions must exist before the first task starts
  depends_on = [
    aws_iam_role_policy_attachment.execution,
    aws_iam_role_policy.read_database_url,
  ]
}

# The API has no authentication yet, so it is only reachable from the address
# that runs "terraform apply". If your IP changes, run apply again.
data "http" "my_ip" {
  url = "https://checkip.amazonaws.com"
}

resource "aws_vpc_security_group_ingress_rule" "api_from_my_ip" {
  security_group_id = aws_security_group.api.id
  description       = "API port from my own IP address only"
  ip_protocol       = "tcp"
  from_port         = 5000
  to_port           = 5000
  cidr_ipv4         = "${chomp(data.http.my_ip.response_body)}/32"
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}
