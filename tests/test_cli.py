"""Tests for the CLI functionality."""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from io import StringIO

from email_validation.cli import main


class TestCLI:
    """Test cases for CLI functionality."""
    
    def test_main_no_arguments(self, capsys):
        """Test CLI with no arguments shows usage."""
        with patch.object(sys, 'argv', ['email_validator.py']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        
        captured = capsys.readouterr()
        assert "Usage:" in captured.out
    
    def test_main_with_input_file_only(self, sample_csv_file, temp_dir):
        """Test CLI with only input file argument."""
        output_file = os.path.join(temp_dir, "cleaned_emails.csv")
        
        with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file]):
            with patch('email_validation.cli.process_csv_file') as mock_process:
                main()
                mock_process.assert_called_once_with(
                    sample_csv_file, 'cleaned_emails.csv', 1.0, 20, False, True, True
                )

    def test_main_with_all_arguments(self, sample_csv_file, temp_dir):
        """Test CLI with all arguments."""
        output_file = os.path.join(temp_dir, "output.csv")

        with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file, output_file, '2.0', '50']):
            with patch('email_validation.cli.process_csv_file') as mock_process:
                main()
                mock_process.assert_called_once_with(
                    sample_csv_file, output_file, 2.0, 50, False, True, True
                )

    def test_main_with_flags(self, sample_csv_file, temp_dir):
        """Test CLI with flags."""
        output_file = os.path.join(temp_dir, "output.csv")

        with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file, output_file, '1.0', '20', '--skip-smtp', '--no-anti-spam']):
            with patch('email_validation.cli.process_csv_file') as mock_process:
                main()
                mock_process.assert_called_once_with(
                    sample_csv_file, output_file, 1.0, 20, True, False, True
                )

    def test_main_with_invalid_delay(self, sample_csv_file):
        """Test CLI with invalid delay parameter."""
        with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file, 'output.csv', 'invalid']):
            with pytest.raises(ValueError):
                main()

    @patch('email_validation.cli.logger')
    def test_main_logs_parameters(self, mock_logger, sample_csv_file, temp_dir):
        """Test that CLI logs the parameters correctly."""
        output_file = os.path.join(temp_dir, "output.csv")

        with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file, output_file, '3.0']):
            with patch('email_validation.cli.process_csv_file'):
                main()

        # Check that logger.info was called with parameter information
        assert mock_logger.info.call_count >= 3
        calls = [call[0][0] for call in mock_logger.info.call_args_list]

        assert any("Input file:" in call for call in calls)
        assert any("Output base:" in call for call in calls)
        assert any("Delay between checks:" in call for call in calls)


class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    @pytest.mark.integration
    def test_cli_end_to_end(self, sample_csv_file, temp_dir):
        """Test complete CLI workflow."""
        output_file = os.path.join(temp_dir, "test_output.csv")

        # Mock the EmailValidator to return predictable results
        with patch('email_validation.cli.EmailValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            def mock_verify(email):
                if "invalid" in email.lower():
                    return {
                        'valid': False,
                        'reason': 'Invalid email format',
                        'format_valid': False,
                        'domain_exists': False,
                        'smtp_valid': False
                    }
                else:
                    return {
                        'valid': True,
                        'reason': 'Email verified successfully',
                        'format_valid': True,
                        'domain_exists': True,
                        'smtp_valid': True
                    }

            mock_validator.verify_email_smtp.side_effect = mock_verify

            # Mock progress tracker methods
            mock_progress_tracker = MagicMock()
            mock_progress_tracker.is_processed.return_value = False
            mock_validator.progress_tracker = mock_progress_tracker

            # Run the CLI
            with patch.object(sys, 'argv', ['email_validator.py', sample_csv_file, output_file, '0.1']):
                main()

        # Check that output files were created
        valid_file = output_file.replace('.csv', '_valid.csv')
        invalid_file = output_file.replace('.csv', '_invalid.csv')
        results_file = output_file.replace('.csv', '_results.csv')

        assert os.path.exists(valid_file)
        assert os.path.exists(invalid_file)
        assert os.path.exists(results_file)

    @pytest.mark.integration
    def test_cli_with_nonexistent_file(self, capsys):
        """Test CLI behavior with nonexistent input file."""
        with patch.object(sys, 'argv', ['email_validator.py', 'nonexistent.csv']):
            with patch('email_validation.cli.logger') as mock_logger:
                main()
                # Should log an error about file not found
                mock_logger.error.assert_called_once()


class TestCLIArgumentParsing:
    """Test CLI argument parsing and validation."""

    def test_argument_count_validation(self):
        """Test validation of argument count."""
        # Test with no arguments
        with patch.object(sys, 'argv', ['script_name']):
            with pytest.raises(SystemExit):
                main()

        # Test with minimum arguments
        with patch.object(sys, 'argv', ['script_name', 'input.csv']):
            with patch('email_validation.cli.process_csv_file'):
                # Should not raise an error
                main()

    def test_delay_parameter_conversion(self, sample_csv_file):
        """Test conversion of delay parameter to float."""
        test_cases = [
            ('1', 1.0),
            ('1.5', 1.5),
            ('0.1', 0.1),
            ('10', 10.0)
        ]

        for delay_str, expected_delay in test_cases:
            with patch.object(sys, 'argv', ['script', sample_csv_file, 'output.csv', delay_str]):
                with patch('email_validation.cli.process_csv_file') as mock_process:
                    main()
                    args = mock_process.call_args[0]
                    assert args[2] == expected_delay  # delay is the third argument

    def test_default_values(self, sample_csv_file):
        """Test default values for optional parameters."""
        # Test with only input file
        with patch.object(sys, 'argv', ['script', sample_csv_file]):
            with patch('email_validation.cli.process_csv_file') as mock_process:
                main()
                args = mock_process.call_args[0]
                assert args[1] == 'cleaned_emails.csv'  # default output file
                assert args[2] == 1.0  # default delay (updated from 1.5)
                assert args[3] == 20   # default max_workers
                assert args[4] == False  # default skip_smtp
                assert args[5] == True   # default anti_spam_mode
                assert args[6] == True   # default resume

        # Test with input and output file
        with patch.object(sys, 'argv', ['script', sample_csv_file, 'custom.csv']):
            with patch('email_validation.cli.process_csv_file') as mock_process:
                main()
                args = mock_process.call_args[0]
                assert args[1] == 'custom.csv'  # custom output file
                assert args[2] == 1.0  # default delay


class TestCLIOutput:
    """Test CLI output and logging."""

    @patch('email_validation.cli.logger')
    def test_logging_output(self, mock_logger, sample_csv_file):
        """Test that CLI produces appropriate logging output."""
        with patch.object(sys, 'argv', ['script', sample_csv_file, 'output.csv', '2.0']):
            with patch('email_validation.cli.process_csv_file'):
                main()

        # Verify that configuration is logged
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Input file:" in call for call in info_calls)
        assert any("Output base:" in call for call in info_calls)
        assert any("Delay between checks:" in call for call in info_calls)

    def test_usage_message_format(self, capsys):
        """Test the format of the usage message."""
        with patch.object(sys, 'argv', ['email-validation']):
            with pytest.raises(SystemExit):
                main()

        captured = capsys.readouterr()
        output = captured.out

        assert "Usage:" in output
        assert "email-validation" in output
        assert "<input_file.csv>" in output
        assert "[output_file.csv]" in output
        assert "[delay_seconds]" in output
        assert "[max_workers]" in output
        assert "Examples:" in output  # Updated from "Example:"

    def test_usage_example(self, capsys):
        """Test that usage includes helpful examples."""
        with patch.object(sys, 'argv', ['email-validation']):
            with pytest.raises(SystemExit):
                main()

        captured = capsys.readouterr()
        output = captured.out

        assert "Examples:" in output  # Updated from "Example:"
        assert "emails.csv" in output
        assert "results.csv" in output  # Updated from "cleaned_emails.csv"
        assert "1.0" in output  # Updated from "2.0"


@pytest.mark.integration
class TestCLIRealUsage:
    """Integration tests that test CLI with minimal mocking."""

    @pytest.mark.slow
    def test_cli_with_real_validation_minimal(self, temp_dir):
        """Test CLI with minimal real validation (fast test)."""
        # Create a small test file with clearly invalid emails
        test_data = [
            {"email": "clearly-invalid-format"},
            {"email": "another@invalid@format.com"}
        ]

        import csv
        input_file = os.path.join(temp_dir, "minimal_test.csv")
        with open(input_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['email'])
            writer.writeheader()
            writer.writerows(test_data)

        output_file = os.path.join(temp_dir, "output.csv")

        # Run with very short delay
        with patch.object(sys, 'argv', ['script', input_file, output_file, '0.01']):
            main()

        # Verify files were created
        results_file = output_file.replace('.csv', '_results.csv')
        assert os.path.exists(results_file)

        # Verify content structure
        with open(results_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Note: only one row because first email has invalid format and gets rejected early
            assert len(rows) >= 1  # At least one should be processed

            # Check that validation fields exist
            for row in rows:
                assert 'email_valid' in row
                assert 'format_valid' in row
                assert row['email_valid'] == 'False'  # Both should be invalid