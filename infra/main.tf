resource "random_id" "this" {
  byte_length = 4

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

resource "random_pet" "this" {
  length    = 3
  separator = "-"

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

# Initial password of the first admin account (cloud only; LocalStack uses a documented
# local default). Shown once via `terraform output -raw bootstrap_admin_password`.
resource "random_password" "admin" {
  length  = 16
  special = false
  # The API refuses a password without a lowercase letter, an uppercase letter and a digit, and then
  # cannot create its first admin. Without these, about 1 deploy in 16 generates a digit-free password.
  min_lower   = 1
  min_upper   = 1
  min_numeric = 1

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

# Signing secret for the API's JWT access tokens. Lives only in Terraform
# state and the Lambda environment; stable per app code, like random_pet.
resource "random_password" "jwt" {
  length  = 64
  special = false

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}
