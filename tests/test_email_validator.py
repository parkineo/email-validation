"""Unit tests for EmailValidator class."""

import pytest
from unittest.mock import patch, MagicMock
import smtplib
import socket
import dns.resolver

from email_validation.cli import EmailValidator


class TestEmailValidator:
    """Test cases for EmailValidator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = EmailValidator(timeout=5, delay=0.1, anti_spam_mode=False)

    def test_init(self):
        """Test EmailValidator initialization."""
        validator = EmailValidator(timeout=10, delay=2)
        assert validator.timeout == 10
        assert validator.delay == 2

    def test_init_defaults(self):
        """Test EmailValidator initialization with defaults."""
        validator = EmailValidator()
        assert validator.timeout == 10
        assert validator.delay == 1

    # Format validation tests
    def test_is_valid_format_valid_emails(self):
        """Test format validation with valid emails."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
            "user_name@test-domain.com",
            "123@example.com",
            "test@sub.domain.com",
            "a@b.co"
        ]

        for email in valid_emails:
            assert self.validator.is_valid_format(email), f"Email {email} should be valid"

    def test_is_valid_format_invalid_emails(self):
        """Test format validation with invalid emails."""
        invalid_emails = [
            "invalid-email",
            "@domain.com",
            "user@",
            "user@@domain.com",
            "user name@domain.com",
            "user@domain",
            "",
            "user@.com",
            "user@domain.",
            "user@domain..com"
        ]

        for email in invalid_emails:
            assert not self.validator.is_valid_format(email), f"Email {email} should be invalid"

    # MX record tests
    @patch('dns.resolver.resolve')
    def test_get_mx_record_success(self, mock_resolve):
        """Test successful MX record lookup."""
        mock_mx = MagicMock()
        mock_mx.preference = 10
        mock_mx.exchange = "mail.example.com."
        mock_resolve.return_value = [mock_mx1, mock_mx2]

        result = self.validator.get_mx_record("example.com")
        assert result == "mail1.example.com"  # Should return highest priority (lowest number)

    @patch('dns.resolver.resolve')
    def test_get_mx_record_failure(self, mock_resolve):
        """Test MX record lookup failure."""
        mock_resolve.side_effect = dns.resolver.NXDOMAIN()

        result = self.validator.get_mx_record("nonexistent.domain")
        assert result is None

    # SMTP verification tests
    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_success(self, mock_smtp_class, mock_get_mx):
        """Test successful SMTP verification."""
        # Use anti_spam_mode=False to get predictable results
        validator = EmailValidator(anti_spam_mode=False)

        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.return_value = (250, "OK")
        mock_smtp_class.return_value = mock_smtp

        result = validator.verify_email_smtp("test@example.com")

        assert result['email'] == "test@example.com"
        assert result['valid'] is True
        assert result['format_valid'] is True
        assert result['domain_exists'] is True
        assert result['smtp_valid'] is True
        assert result['reason'] == "Email verified successfully"

        # Verify SMTP calls - with anti_spam_mode=False, should use defaults
        mock_smtp.connect.assert_called_once_with("mail.example.com", 25)
        mock_smtp.helo.assert_called_once_with('gmail.com')
        mock_smtp.mail.assert_called_once_with('test@gmail.com')
        mock_smtp.rcpt.assert_called_once_with("test@example.com")
        mock_smtp.quit.assert_called_once()

    def test_verify_email_smtp_invalid_format(self):
        """Test SMTP verification with invalid format."""
        result = self.validator.verify_email_smtp("invalid-email")

        assert result['email'] == "invalid-email"
        assert result['valid'] is False
        assert result['format_valid'] is False
        assert result['domain_exists'] is False
        assert result['smtp_valid'] is False
        assert result['reason'] == "Invalid email format"

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    def test_verify_email_smtp_no_mx_record(self, mock_get_mx):
        """Test SMTP verification with no MX record."""
        mock_get_mx.return_value = None

        result = self.validator.verify_email_smtp("test@nonexistent.com")

        assert result['email'] == "test@nonexistent.com"
        assert result['valid'] is False
        assert result['format_valid'] is True
        assert result['domain_exists'] is False
        assert result['smtp_valid'] is False
        assert result['reason'] == "No MX record found"

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_rejected(self, mock_smtp_class, mock_get_mx):
        """Test SMTP verification with rejected email."""
        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.return_value = (550, "User unknown")
        mock_smtp_class.return_value = mock_smtp

        result = self.validator.verify_email_smtp("invalid@example.com")

        assert result['email'] == "invalid@example.com"
        assert result['valid'] is False
        assert result['format_valid'] is True
        assert result['domain_exists'] is True
        assert result['smtp_valid'] is False
        assert "SMTP rejected: 550" in result['reason']

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_recipients_refused(self, mock_smtp_class, mock_get_mx):
        """Test SMTP verification with recipients refused."""
        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.side_effect = smtplib.SMTPRecipientsRefused({})
        mock_smtp_class.return_value = mock_smtp

        result = self.validator.verify_email_smtp("refused@example.com")

        assert result['valid'] is False
        # Updated to match actual error format
        assert result['reason'] == "SMTP error: SMTPRecipientsRefused"

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_server_disconnected(self, mock_smtp_class, mock_get_mx):
        """Test SMTP verification with server disconnection."""
        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.side_effect = smtplib.SMTPServerDisconnected()
        mock_smtp_class.return_value = mock_smtp

        result = self.validator.verify_email_smtp("test@example.com")

        assert result['valid'] is False
        # Updated to match actual error format
        assert result['reason'] == "SMTP error: SMTPServerDisconnected"

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_timeout(self, mock_smtp_class, mock_get_mx):
        """Test SMTP verification with timeout."""
        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.side_effect = socket.timeout()
        mock_smtp_class.return_value = mock_smtp

        result = self.validator.verify_email_smtp("test@example.com")

        assert result['valid'] is False
        # Updated to match actual error format (socket.timeout becomes TimeoutError)
        assert result['reason'] == "SMTP error: TimeoutError"

    @patch('email_validation.cli.EmailValidator.get_mx_record')
    @patch('smtplib.SMTP')
    def test_verify_email_smtp_general_exception(self, mock_smtp_class, mock_get_mx):
        """Test SMTP verification with general exception."""
        mock_get_mx.return_value = "mail.example.com"

        mock_smtp = MagicMock()
        mock_smtp.rcpt.side_effect = Exception("Network error")
        mock_smtp_class.return_value = mock_smtp

        result = self.validator.verify_email_smtp("test@example.com")

        assert result['valid'] is False
        assert "SMTP error: Network error" in result['reason']

    def test_anti_spam_mode_randomization(self):
        """Test that anti-spam mode uses random values."""
        validator = EmailValidator(anti_spam_mode=True)

        # Test that random choices are available
        assert len(validator.helo_domains) > 1
        assert len(validator.sender_emails) > 1
        assert len(validator.user_agents) > 1

    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        validator = EmailValidator(anti_spam_mode=True)

        # Test rate limit check
        domain = "example.com"

        # Should allow requests initially
        assert validator._check_rate_limit(domain) is True

        # Fill up the rate limit
        validator.requests_per_domain[domain] = validator.max_requests_per_hour

        # Should block further requests
        assert validator._check_rate_limit(domain) is False

    def test_domain_delay_handling(self):
        """Test domain-specific delay handling."""
        validator = EmailValidator()

        domain = "example.com"
        email = f"test@{domain}"

        # Initial delay should be default
        assert validator.get_domain_delay(email) == validator.delay

        # Simulate errors to increase delay
        validator._handle_domain_error(domain)
        validator._handle_domain_error(domain)
        validator._handle_domain_error(domain)
        validator._handle_domain_error(domain)  # Trigger increase

        # Delay should be increased
        assert validator.get_domain_delay(email) > validator.delay


@pytest.mark.integration
class TestEmailValidatorIntegration:
    """Integration tests for EmailValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = EmailValidator(timeout=5, delay=0.1, anti_spam_mode=False)

    @pytest.mark.slow
    def test_verify_known_good_email(self):
        """Test verification of a known good email domain."""
        # Using a well-known domain that should have MX records
        result = self.validator.verify_email_smtp("nonexistent@gmail.com")

        # Should pass format and domain checks, may fail on SMTP
        assert result['format_valid'] is True
        assert result['domain_exists'] is True
        # SMTP result may vary, so we don't assert on it

    @pytest.mark.slow
    def test_verify_known_bad_domain(self):
        """Test verification of a domain that doesn't exist."""
        result = self.validator.verify_email_smtp("test@thisdefinitelydoesnotexist12345.com")

        assert result['format_valid'] is True
        assert result['domain_exists'] is False
        assert result['smtp_valid'] is False
        assert result['valid'] is False_value = [mock_mx]

        result = self.validator.get_mx_record("example.com")
        assert result == "mail.example.com"
        mock_resolve.assert_called_once_with("example.com", 'MX')

    @patch('dns.resolver.resolve')
    def test_get_mx_record_multiple_records(self, mock_resolve):
        """Test MX record lookup with multiple records."""
        mock_mx1 = MagicMock()
        mock_mx1.preference = 20
        mock_mx1.exchange = "mail2.example.com."

        mock_mx2 = MagicMock()
        mock_mx2.preference = 10
        mock_mx2.exchange = "mail1.example.com."

        mock_resolve.return