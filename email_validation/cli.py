#!/usr/bin/env python3
"""
Email validation script using SMTP verification
Reads CSV file, validates emails, and outputs cleaned data with validation results
"""

import csv
import smtplib
import socket
import dns.resolver
import re
import time
import sys
from typing import Dict, List, Tuple
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EmailValidator:
    def __init__(self, timeout=10, delay=1):
        self.timeout = timeout
        self.delay = delay  # Delay between checks to avoid being blocked

    def is_valid_format(self, email: str) -> bool:
        """Basic email format validation"""
        pattern = r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
        return re.match(pattern, email) is not None

    def get_mx_record(self, domain: str) -> str:
        """Get MX record for domain"""
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            # Sort by priority and return the highest priority (lowest number)
            mx_record = sorted(mx_records, key=lambda x: x.preference)[0]
            return str(mx_record.exchange).rstrip('.')
        except Exception as e:
            logger.debug(f"No MX record found for {domain}: {e}")
            return None

    def verify_email_smtp(self, email: str) -> Dict[str, any]:
        """
        Verify email using SMTP
        Returns dict with validation result and details
        """
        result = {
            'email': email,
            'valid': False,
            'reason': '',
            'format_valid': False,
            'domain_exists': False,
            'smtp_valid': False
        }

        # Step 1: Format validation
        if not self.is_valid_format(email):
            result['reason'] = 'Invalid email format'
            return result

        result['format_valid'] = True

        try:
            domain = email.split('@')[1].lower()

            # Step 2: Get MX record
            mx_record = self.get_mx_record(domain)
            if not mx_record:
                result['reason'] = 'No MX record found'
                return result

            result['domain_exists'] = True

            # Step 3: SMTP verification
            try:
                # Connect to SMTP server
                server = smtplib.SMTP(timeout=self.timeout)
                server.set_debuglevel(0)  # Set to 1 for debugging

                # Connect and say hello
                server.connect(mx_record, 25)
                server.helo('gmail.com')  # Use a common domain

                # Set sender
                server.mail('test@gmail.com')

                # Test recipient
                code, message = server.rcpt(email)
                server.quit()

                if code == 250:
                    result['valid'] = True
                    result['smtp_valid'] = True
                    result['reason'] = 'Email verified successfully'
                else:
                    result['reason'] = f'SMTP rejected: {code} {message}'

            except smtplib.SMTPRecipientsRefused:
                result['reason'] = 'Email address rejected by server'
            except smtplib.SMTPServerDisconnected:
                result['reason'] = 'SMTP server disconnected'
            except socket.timeout:
                result['reason'] = 'SMTP connection timeout'
            except Exception as e:
                result['reason'] = f'SMTP error: {str(e)}'

        except Exception as e:
            result['reason'] = f'General error: {str(e)}'

        return result


def process_csv_file(input_file: str, output_file: str, delay: float = 1.5):
    """
    Process CSV file and validate emails
    """
    validator = EmailValidator(delay=delay)

    valid_emails = []
    invalid_emails = []

    try:
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            total_rows = sum(1 for line in open(input_file, encoding='utf-8')) - 1  # Subtract header
            logger.info(f"Processing {total_rows} emails...")

            # Reset file pointer
            csvfile.seek(0)
            reader = csv.DictReader(csvfile)

            for i, row in enumerate(reader, 1):
                email = row['email'].strip().lower()

                logger.info(f"Processing {i}/{total_rows}: {email}")

                # Validate email
                validation_result = validator.verify_email_smtp(email)

                # Add validation info to row
                row_with_validation = row.copy()
                row_with_validation.update({
                    'email_original': row['email'],  # Keep original case
                    'email': email,  # Normalized email
                    'email_valid': validation_result['valid'],
                    'validation_reason': validation_result['reason'],
                    'format_valid': validation_result['format_valid'],
                    'domain_exists': validation_result['domain_exists'],
                    'smtp_valid': validation_result['smtp_valid']
                })

                if validation_result['valid']:
                    valid_emails.append(row_with_validation)
                    logger.info(f"✓ Valid: {email}")
                else:
                    invalid_emails.append(row_with_validation)
                    logger.info(f"✗ Invalid: {email} - {validation_result['reason']}")

                # Add delay to avoid being blocked
                if i < total_rows:
                    time.sleep(delay)

    except FileNotFoundError:
        logger.error(f"Input file '{input_file}' not found")
        return
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        return

    # Write results
    write_results(valid_emails, invalid_emails, output_file)

    # Print summary
    total = len(valid_emails) + len(invalid_emails)
    if total == 0:
        logger.warning("No emails were processed.")
        return
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"Total emails processed: {total}")
    logger.info(f"Valid emails: {len(valid_emails)} ({len(valid_emails) / total * 100:.1f}%)")
    logger.info(f"Invalid emails: {len(invalid_emails)} ({len(invalid_emails) / total * 100:.1f}%)")


def write_results(valid_emails: List[Dict], invalid_emails: List[Dict], base_filename: str):
    """Write results to separate files"""

    if not valid_emails and not invalid_emails:
        logger.warning("No data to write")
        return

    # Get fieldnames (assuming all rows have same structure)
    all_emails = valid_emails + invalid_emails
    if all_emails:
        fieldnames = list(all_emails[0].keys())

    # Write valid emails
    if valid_emails:
        valid_filename = base_filename.replace('.csv', '_valid.csv')
        with open(valid_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(valid_emails)
        logger.info(f"Valid emails written to: {valid_filename}")

    # Write invalid emails
    if invalid_emails:
        invalid_filename = base_filename.replace('.csv', '_invalid.csv')
        with open(invalid_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(invalid_emails)
        logger.info(f"Invalid emails written to: {invalid_filename}")

    # Write combined results
    combined_filename = base_filename.replace('.csv', '_results.csv')
    with open(combined_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_emails)
    logger.info(f"Combined results written to: {combined_filename}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python email_validator.py <input_file.csv> [output_file.csv] [delay_seconds]")
        print("Example: python email_validator.py emails.csv cleaned_emails.csv 2.0")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'cleaned_emails.csv'
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5

    logger.info(f"Input file: {input_file}")
    logger.info(f"Output base: {output_file}")
    logger.info(f"Delay between checks: {delay} seconds")

    process_csv_file(input_file, output_file, delay)


if __name__ == "__main__":
    main()