"""Integration tests for CSV processing functionality."""

import pytest
import csv
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from email_validation.cli import process_csv_file, write_results


class TestCSVProcessing:
    """Test cases for CSV processing functionality."""
    
    def create_test_csv(self, data, filename="test_emails.csv"):
        """Helper method to create test CSV files."""
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, filename)
        
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        
        return file_path, temp_dir
    
    def test_process_csv_file_basic(self):
        """Test basic CSV processing."""
        test_data = [
            {"email": "test1@example.com", "name": "Test User 1"},
            {"email": "test2@example.com", "name": "Test User 2"},
            {"email": "invalid-email", "name": "Invalid User"}
        ]
        
        input_file, temp_dir = self.create_test_csv(test_data)
        output_file = os.path.join(temp_dir, "output.csv")
        
        # Mock the email validator to return predictable results
        with patch('email_validation.cli.EmailValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator
            
            # Mock progress tracker
            mock_progress_tracker = MagicMock()
            mock_progress_tracker.is_processed.return_value = False
            mock_validator.progress_tracker = mock_progress_tracker

            # Mock validation results
            def mock_verify(email):
                if email == "test1@example.com":
                    return {
                        'valid': True,
                        'reason': 'Email verified successfully',
                        'format_valid': True,
                        'domain_exists': True,
                        'smtp_valid': True
                    }
                elif email == "test2@example.com":
                    return {
                        'valid': True,
                        'reason': 'Email verified successfully',
                        'format_valid': True,
                        'domain_exists': True,
                        'smtp_valid': True
                    }
                else:
                    return {
                        'valid': False,
                        'reason': 'Invalid email format',
                        'format_valid': False,
                        'domain_exists': False,
                        'smtp_valid': False
                    }

            mock_validator.verify_email_smtp.side_effect = mock_verify
            mock_validator.get_domain_delay.return_value = 0.1

            # Process the CSV with all required parameters
            process_csv_file(input_file, output_file, delay=0.1, max_workers=1,
                           skip_smtp=False, anti_spam_mode=False, resume=False)

        # Check that output files were created
        valid_file = output_file.replace('.csv', '_valid.csv')
        invalid_file = output_file.replace('.csv', '_invalid.csv')
        results_file = output_file.replace('.csv', '_results.csv')

        assert os.path.exists(valid_file)
        assert os.path.exists(invalid_file)
        assert os.path.exists(results_file)

        # Check valid emails file
        with open(valid_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            valid_rows = list(reader)
            assert len(valid_rows) == 2
            assert valid_rows[0]['email'] == "test1@example.com"
            assert valid_rows[1]['email'] == "test2@example.com"

        # Check invalid emails file
        with open(invalid_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            invalid_rows = list(reader)
            assert len(invalid_rows) == 1
            assert invalid_rows[0]['email'] == "invalid-email"

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_process_csv_file_nonexistent_input(self):
        """Test processing with nonexistent input file."""
        with patch('email_validation.cli.logger') as mock_logger:
            process_csv_file("nonexistent.csv", "output.csv", delay=0.1, max_workers=1,
                           skip_smtp=False, anti_spam_mode=False, resume=False)
            mock_logger.error.assert_called_once()

    def test_process_csv_file_empty_input(self):
        """Test processing with empty CSV file."""
        # Create empty CSV (header only)
        temp_dir = tempfile.mkdtemp()
        input_file = os.path.join(temp_dir, "empty.csv")

        with open(input_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['email'])
            writer.writeheader()

        output_file = os.path.join(temp_dir, "output.csv")

        with patch('email_validation.cli.EmailValidator'):
            process_csv_file(input_file, output_file, delay=0.1, max_workers=1,
                           skip_smtp=False, anti_spam_mode=False, resume=False)

        # Check that no output files were created (since no data to process)
        valid_file = output_file.replace('.csv', '_valid.csv')
        invalid_file = output_file.replace('.csv', '_invalid.csv')
        results_file = output_file.replace('.csv', '_results.csv')

        # Files might exist but should be empty or minimal
        if os.path.exists(results_file):
            with open(results_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Should only contain header or be empty
                assert len(content.split('\n')) <= 1

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_write_results_functionality(self):
        """Test the write_results function directly."""
        valid_emails = [
            {
                'email': 'valid@example.com',
                'name': 'Valid User',
                'email_valid': True,
                'validation_reason': 'Email verified successfully'
            }
        ]

        invalid_emails = [
            {
                'email': 'invalid@example.com',
                'name': 'Invalid User',
                'email_valid': False,
                'validation_reason': 'Invalid email format'
            }
        ]

        temp_dir = tempfile.mkdtemp()
        base_filename = os.path.join(temp_dir, "test_results.csv")

        write_results(valid_emails, invalid_emails, base_filename)

        # Check all three files were created
        valid_file = base_filename.replace('.csv', '_valid.csv')
        invalid_file = base_filename.replace('.csv', '_invalid.csv')
        results_file = base_filename.replace('.csv', '_results.csv')

        assert os.path.exists(valid_file)
        assert os.path.exists(invalid_file)
        assert os.path.exists(results_file)

        # Verify content of valid file
        with open(valid_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]['email'] == 'valid@example.com'
            assert rows[0]['email_valid'] == 'True'

        # Verify content of invalid file
        with open(invalid_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]['email'] == 'invalid@example.com'
            assert rows[0]['email_valid'] == 'False'

        # Verify content of results file (combined)
        with open(results_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_write_results_empty_data(self):
        """Test write_results with empty data."""
        temp_dir = tempfile.mkdtemp()
        base_filename = os.path.join(temp_dir, "empty_results.csv")

        with patch('email_validation.cli.logger') as mock_logger:
            write_results([], [], base_filename)
            mock_logger.warning.assert_called_once_with("No data to write")

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_write_results_only_valid(self):
        """Test write_results with only valid emails."""
        valid_emails = [
            {
                'email': 'valid@example.com',
                'name': 'Valid User',
                'email_valid': True
            }
        ]

        temp_dir = tempfile.mkdtemp()
        base_filename = os.path.join(temp_dir, "valid_only.csv")

        write_results(valid_emails, [], base_filename)

        valid_file = base_filename.replace('.csv', '_valid.csv')
        invalid_file = base_filename.replace('.csv', '_invalid.csv')
        results_file = base_filename.replace('.csv', '_results.csv')

        assert os.path.exists(valid_file)
        assert not os.path.exists(invalid_file)  # Should not create invalid file
        assert os.path.exists(results_file)

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_write_results_only_invalid(self):
        """Test write_results with only invalid emails."""
        invalid_emails = [
            {
                'email': 'invalid@example.com',
                'name': 'Invalid User',
                'email_valid': False
            }
        ]

        temp_dir = tempfile.mkdtemp()
        base_filename = os.path.join(temp_dir, "invalid_only.csv")

        write_results([], invalid_emails, base_filename)

        valid_file = base_filename.replace('.csv', '_valid.csv')
        invalid_file = base_filename.replace('.csv', '_invalid.csv')
        results_file = base_filename.replace('.csv', '_results.csv')

        assert not os.path.exists(valid_file)  # Should not create valid file
        assert os.path.exists(invalid_file)
        assert os.path.exists(results_file)

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


@pytest.mark.integration
class TestCSVProcessingIntegration:
    """Integration tests for CSV processing with real validation."""

    def create_test_csv(self, data, filename="test_emails.csv"):
        """Helper method to create test CSV files."""
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, filename)

        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        return file_path, temp_dir

    @pytest.mark.slow
    def test_process_csv_with_mixed_emails(self):
        """Test CSV processing with mix of valid/invalid emails."""
        test_data = [
            {"email": "INVALID@FORMAT", "name": "Invalid Format"},
            {"email": "test@nonexistentdomain12345.com", "name": "Nonexistent Domain"},
            {"email": "test@gmail.com", "name": "Valid Format Domain"}  # Should pass format/domain checks
        ]

        input_file, temp_dir = self.create_test_csv(test_data)
        output_file = os.path.join(temp_dir, "output.csv")

        # Process with real validation but very short delay
        process_csv_file(input_file, output_file, delay=0.1, max_workers=1,
                       skip_smtp=False, anti_spam_mode=False, resume=False)
        
        # Check that files were created
        results_file = output_file.replace('.csv', '_results.csv')
        assert os.path.exists(results_file)
        
        # Read results and verify structure
        with open(results_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3
            
            # Check that validation fields were added
            expected_fields = ['email', 'name', 'email_original', 'email_valid', 
                             'validation_reason', 'format_valid', 'domain_exists', 'smtp_valid']
            for field in expected_fields:
                assert field in reader.fieldnames
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)