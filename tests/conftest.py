"""Pytest configuration and fixtures for email validation tests."""

import pytest
import tempfile
import os
import csv
import shutil
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing."""
    return [
        {"email": "valid@example.com", "name": "Valid User", "company": "Example Corp"},
        {"email": "another@test.com", "name": "Another User", "company": "Test Inc"},
        {"email": "invalid-email", "name": "Invalid User", "company": "Bad Corp"},
        {"email": "test@nonexistent.xyz", "name": "Nonexistent Domain", "company": "Fake Co"},
        {"email": "USER@UPPERCASE.COM", "name": "Uppercase User", "company": "Upper Corp"}
    ]


@pytest.fixture
def sample_csv_file(temp_dir, sample_csv_data):
    """Create a sample CSV file for testing."""
    file_path = os.path.join(temp_dir, "test_emails.csv")
    
    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=sample_csv_data[0].keys())
        writer.writeheader()
        writer.writerows(sample_csv_data)
    
    return file_path


@pytest.fixture
def empty_csv_file(temp_dir):
    """Create an empty CSV file (header only) for testing."""
    file_path = os.path.join(temp_dir, "empty_emails.csv")
    
    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['email', 'name'])
        writer.writeheader()
    
    return file_path


@pytest.fixture
def malformed_csv_file(temp_dir):
    """Create a malformed CSV file for testing error handling."""
    file_path = os.path.join(temp_dir, "malformed_emails.csv")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("This is not a proper CSV file\n")
        f.write("It has no headers\n")
        f.write("And malformed data\n")
    
    return file_path


@pytest.fixture
def valid_email_result():
    """Sample valid email validation result."""
    return {
        'email': 'test@example.com',
        'valid': True,
        'reason': 'Email verified successfully',
        'format_valid': True,
        'domain_exists': True,
        'smtp_valid': True
    }


@pytest.fixture
def invalid_format_result():
    """Sample invalid format validation result."""
    return {
        'email': 'invalid-email',
        'valid': False,
        'reason': 'Invalid email format',
        'format_valid': False,
        'domain_exists': False,
        'smtp_valid': False
    }


@pytest.fixture
def no_mx_result():
    """Sample no MX record validation result."""
    return {
        'email': 'test@nonexistent.com',
        'valid': False,
        'reason': 'No MX record found',
        'format_valid': True,
        'domain_exists': False,
        'smtp_valid': False
    }


@pytest.fixture
def smtp_rejected_result():
    """Sample SMTP rejected validation result."""
    return {
        'email': 'rejected@example.com',
        'valid': False,
        'reason': 'SMTP rejected: 550 User unknown',
        'format_valid': True,
        'domain_exists': True,
        'smtp_valid': False
    }


@pytest.fixture
def validation_results_set(valid_email_result, invalid_format_result, no_mx_result, smtp_rejected_result):
    """Set of various validation results for testing."""
    return {
        'valid@example.com': valid_email_result,
        'invalid-email': invalid_format_result,
        'test@nonexistent.com': no_mx_result,
        'rejected@example.com': smtp_rejected_result
    }


class MockEmailValidator:
    """Mock EmailValidator for testing."""
    
    def __init__(self, timeout=10, delay=1):
        self.timeout = timeout
        self.delay = delay
        self.call_count = 0
    
    def is_valid_format(self, email):
        """Mock format validation."""
        return '@' in email and '.' in email.split('@')[-1]
    
    def get_mx_record(self, domain):
        """Mock MX record lookup."""
        # Simulate some domains having MX records
        known_domains = ['example.com', 'test.com', 'gmail.com', 'yahoo.com']
        return f"mail.{domain}" if domain in known_domains else None
    
    def verify_email_smtp(self, email):
        """Mock SMTP verification with predictable results."""
        self.call_count += 1
        
        # Predictable results based on email patterns
        if not self.is_valid_format(email):
            return {
                'email': email,
                'valid': False,
                'reason': 'Invalid email format',
                'format_valid': False,
                'domain_exists': False,
                'smtp_valid': False
            }
        
        domain = email.split('@')[1]
        
        if not self.get_mx_record(domain):
            return {
                'email': email,
                'valid': False,
                'reason': 'No MX record found',
                'format_valid': True,
                'domain_exists': False,
                'smtp_valid': False
            }
        
        # For testing purposes, reject emails with 'reject' in them
        if 'reject' in email.lower():
            return {
                'email': email,
                'valid': False,
                'reason': 'SMTP rejected: 550 User unknown',
                'format_valid': True,
                'domain_exists': True,
                'smtp_valid': False
            }
        
        # Otherwise, consider it valid
        return {
            'email': email,
            'valid': True,
            'reason': 'Email verified successfully',
            'format_valid': True,
            'domain_exists': True,
            'smtp_valid': True
        }


@pytest.fixture
def mock_email_validator():
    """Provide a mock EmailValidator instance."""
    return MockEmailValidator()


# Pytest markers for test categorization
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may take several seconds)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their names and locations."""
    for item in items:
        # Mark integration tests
        if "integration" in item.nodeid.lower() or "test_integration" in item.name:
            item.add_marker(pytest.mark.integration)
        
        # Mark slow tests
        if "slow" in item.name or "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
        
        # Mark unit tests (default for most tests)
        if not any(marker.name in ["integration", "slow"] for marker in item.iter_markers()):
            item.add_marker(pytest.mark.unit)