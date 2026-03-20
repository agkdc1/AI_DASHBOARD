terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "your-project-tfstate"
    prefix = "terraform/aws"
  }
}

provider "aws" {
  region = "ap-northeast-1"
}
