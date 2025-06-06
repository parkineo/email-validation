# Email Validation

A comprehensive Python library for email validation that performs multi-stage verification including format validation, DNS MX record lookup, and SMTP verification.

## Features

- **Format Validation**: Validates email format using RFC-compliant regex patterns
- **DNS MX Record Lookup**: Verifies that the domain has valid mail exchange records
- **SMTP Verification**: Tests actual email deliverability by connecting to mail servers
- **CSV Processing**: Bulk validation of email lists with detailed reporting
- **Rate Limiting**: Built-in delays to avoid being blocked by mail servers
- **Detailed Reporting**: Comprehensive validation results with failure reasons
- **Docker Support**: Containerized deployment for scalable processing

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/w6d-io/email-validation.git
cd email-validation

# Install in development mode
pip install -e .

# Install with development dependencies
pip install -e .[dev]
```

### Using Docker

```bash
# Build the Docker image
docker build -t email-validation .

# Run with mounted data directory
docker run -v $(pwd)/data:/app/data email-validation data/emails.csv
```

## Usage

### Command Line Interface

```bash
# Basic usage
email-validation emails.csv

# Specify output file and delay
email-validation emails.csv cleaned_emails.csv 2.0

# Using Python directly
python -m email_validation.cli emails.csv output.csv 1.5
```

### Python API

```python
from email_validation.cli import EmailValidator

# Create validator instance
validator = EmailValidator(timeout=10, delay=1.5)

# Validate single email
result = validator.verify_email_smtp("user@example.com")
print(f"Valid: {result['valid']}")
print(f"Reason: {result['reason']}")

# Check individual validation stages
print(f"Format valid: {result['format_valid']}")
print(f"Domain exists: {result['domain_exists']}")
print(f"SMTP valid: {result['smtp_valid']}")
```

### CSV Input Format

Your CSV file should have an `email` column:

```csv
email,name,company
john@example.com,John Doe,Example Corp
jane@test.com,Jane Smith,Test Inc
invalid-email,Bad Entry,Bad Corp
```

### Output Files

The tool generates three output files:

- `*_valid.csv`: Contains only valid emails with validation details
- `*_invalid.csv`: Contains invalid emails with failure reasons
- `*_results.csv`: Combined results with all validation information

## Validation Process

The email validation follows a three-stage process:

1. **Format Validation**: Checks if the email follows valid format patterns
2. **DNS MX Lookup**: Verifies the domain has mail exchange records
3. **SMTP Verification**: Attempts to connect to the mail server and verify deliverability

Each stage provides detailed feedback, allowing you to understand exactly why an email failed validation.

## Configuration

### Environment Variables

You can use a `.env` file for configuration:

```env
# SMTP timeout in seconds
EMAIL_VALIDATION_TIMEOUT=10

# Delay between validations in seconds
EMAIL_VALIDATION_DELAY=1.5

# Log level
LOG_LEVEL=INFO
```

### Rate Limiting

The validator includes built-in rate limiting to avoid being blocked by mail servers:

- Default delay: 1.5 seconds between validations
- Configurable timeout: 10 seconds for SMTP connections
- Respectful SMTP behavior with proper HELO and cleanup

## Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run tests with coverage
pytest --cov=email_validation

# Format code
black email_validation/
isort email_validation/
```

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test categories
pytest -m "not slow"  # Skip slow tests
pytest -m "integration"  # Run only integration tests
```

### Code Quality

The project uses several tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **pytest**: Testing framework
- **pytest-cov**: Coverage reporting

## Docker Deployment

### Building the Image

```bash
docker build -t email-validation .
```

### Running in Container

```bash
# Basic usage
docker run email-validation

# With mounted data directory
docker run -v /path/to/data:/app/data email-validation data/emails.csv

# With custom delay
docker run email-validation emails.csv output.csv 3.0
```

The Docker container:
- Uses multi-stage build for optimized size
- Runs as non-root user for security
- Includes all necessary dependencies
- Supports volume mounting for data access

## Technical Details

### Dependencies

- **dnspython**: DNS resolution for MX record lookup
- **python-dotenv**: Environment variable management

### SMTP Verification Details

- Uses `test@gmail.com` as sender for compatibility
- Performs HELO with `gmail.com` domain
- Properly closes connections to avoid being blacklisted
- Handles various SMTP response codes and exceptions

### Performance Considerations

- Built-in rate limiting prevents server blocking
- Efficient CSV processing with streaming
- Configurable timeouts for network operations
- Memory-efficient processing of large email lists

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For support and bug reports, please visit the [GitHub Issues](https://github.com/w6d-io/email-validation/issues) page.