# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python email validation library that performs comprehensive email verification using SMTP, DNS MX record lookup, and format validation. The project is structured as both a Python package and a CLI tool with modern Python packaging standards.

## Architecture

- **email_validation/cli.py**: Main email validation module containing the `EmailValidator` class
- **pyproject.toml**: Modern Python packaging configuration with dev dependencies and tool configuration
- **setup.py/setup.cfg**: Legacy package configuration (dual support)
- **Dockerfile**: Multi-stage Docker build for containerized deployment
- **MANIFEST.in**: Package manifest for including additional files

The `EmailValidator` class performs multi-stage validation:
1. Email format validation using regex
2. DNS MX record lookup for domain verification  
3. SMTP connection testing to verify deliverability

## Key Commands

**Install package in development mode with dev dependencies:**
```bash
pip install -e .[dev]
```

**Run tests:**
```bash
pytest
```

**Run tests with coverage:**
```bash
pytest --cov=email_validation
```

**Code formatting:**
```bash
black email_validation/
isort email_validation/
```

**Run CLI tool:**
```bash
email-validation <input_file.csv> [output_file.csv] [delay_seconds]
```

**Docker build and run:**
```bash
docker build -t email-validation .
docker run -v $(pwd)/data:/app/data email-validation data/emails.csv
```

## Development Setup

The project uses modern Python packaging with `pyproject.toml` and includes development dependencies:
- `pytest` and `pytest-cov` for testing
- `black` and `isort` for code formatting
- `python-dotenv` for environment variable management

## Important Implementation Details

- The validator includes rate limiting (`delay` parameter) to avoid being blocked by SMTP servers
- CSV processing creates three output files: `_valid.csv`, `_invalid.csv`, and `_results.csv`
- SMTP verification uses a fake sender (`test@gmail.com`) and Gmail HELO for compatibility
- All validation results include detailed reasons for failures and validation stage results
- Email addresses are normalized to lowercase for processing but original case is preserved
- Docker container runs as non-root user for security