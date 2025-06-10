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
import asyncio
import aiosmtplib
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Optional, Set
import logging
from functools import lru_cache
from collections import defaultdict
import os
import json
import random
from pathlib import Path
import threading

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StreamingCSVWriter:
    """Thread-safe streaming CSV writer for real-time output"""
    def __init__(self, base_filename: str):
        self.base_filename = base_filename
        self.valid_filename = base_filename.replace('.csv', '_valid.csv')
        self.invalid_filename = base_filename.replace('.csv', '_invalid.csv')
        self.results_filename = base_filename.replace('.csv', '_results.csv')
        
        self.lock = threading.Lock()
        self.headers_written = {'valid': False, 'invalid': False, 'results': False}
        
    def write_result(self, result: Dict, fieldnames: List[str]):
        """Write a single result immediately"""
        with self.lock:
            # Write to results file
            self._write_to_file(self.results_filename, result, fieldnames, 'results')
            
            # Write to valid/invalid files
            if result['email_valid']:
                self._write_to_file(self.valid_filename, result, fieldnames, 'valid')
            else:
                self._write_to_file(self.invalid_filename, result, fieldnames, 'invalid')
    
    def _write_to_file(self, filename: str, result: Dict, fieldnames: List[str], file_type: str):
        """Write to specific file with header handling"""
        file_exists = os.path.exists(filename)
        mode = 'a' if file_exists else 'w'
        
        with open(filename, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists or not self.headers_written[file_type]:
                writer.writeheader()
                self.headers_written[file_type] = True
                
            writer.writerow(result)


class ProgressTracker:
    """Track processing progress for resume capability"""
    def __init__(self, progress_file: str):
        self.progress_file = progress_file
        self.processed_emails = set()
        self.load_progress()
    
    def load_progress(self):
        """Load previously processed emails"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    self.processed_emails = set(data.get('processed_emails', []))
                logger.info(f"Loaded progress: {len(self.processed_emails)} emails already processed")
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
    
    def save_progress(self):
        """Save current progress"""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump({'processed_emails': list(self.processed_emails)}, f)
        except Exception as e:
            logger.error(f"Could not save progress: {e}")
    
    def is_processed(self, email: str) -> bool:
        """Check if email was already processed"""
        return email in self.processed_emails
    
    def mark_processed(self, email: str):
        """Mark email as processed"""
        self.processed_emails.add(email)


class EmailValidator:
    def __init__(self, timeout=10, delay=1, max_workers=20, skip_smtp=False, 
                 anti_spam_mode=True, progress_tracker=None):
        self.timeout = timeout
        self.delay = delay
        self.max_workers = max_workers
        self.skip_smtp = skip_smtp
        self.anti_spam_mode = anti_spam_mode
        self.progress_tracker = progress_tracker
        
        self.mx_cache = {}
        self.processed_emails = set()
        self.domain_delays = defaultdict(lambda: delay)
        self.domain_error_counts = defaultdict(int)
        
        # Anti-Spamhaus measures
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        self.helo_domains = ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com']
        self.sender_emails = ['test@gmail.com', 'noreply@outlook.com', 'check@yahoo.com']
        
        # Rate limiting for anti-spam
        self.requests_per_domain = defaultdict(int)
        self.last_request_time = defaultdict(float)
        self.max_requests_per_hour = 100

    def is_valid_format(self, email: str) -> bool:
        """Basic email format validation"""
        pattern = r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
        return re.match(pattern, email) is not None

    def get_mx_record(self, domain: str) -> Optional[str]:
        """Get MX record for domain with caching"""
        if domain in self.mx_cache:
            return self.mx_cache[domain]
        
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_record = sorted(mx_records, key=lambda x: x.preference)[0]
            result = str(mx_record.exchange).rstrip('.')
            self.mx_cache[domain] = result
            return result
        except Exception as e:
            logger.debug(f"No MX record found for {domain}: {e}")
            self.mx_cache[domain] = None
            return None

    def _check_rate_limit(self, domain: str) -> bool:
        """Check if we're hitting rate limits for anti-spam protection"""
        if not self.anti_spam_mode:
            return True
            
        current_time = time.time()
        
        # Reset counter if an hour has passed
        if current_time - self.last_request_time[domain] > 3600:
            self.requests_per_domain[domain] = 0
        
        if self.requests_per_domain[domain] >= self.max_requests_per_hour:
            return False
            
        self.requests_per_domain[domain] += 1
        self.last_request_time[domain] = current_time
        return True

    def verify_email_smtp(self, email: str) -> Dict[str, any]:
        """
        Verify email using SMTP with anti-spam measures and progress tracking
        """
        result = {
            'email': email,
            'valid': False,
            'reason': '',
            'format_valid': False,
            'domain_exists': False,
            'smtp_valid': False
        }

        # Check progress tracker first
        if self.progress_tracker and self.progress_tracker.is_processed(email):
            result['reason'] = 'Already processed (resumed)'
            return result

        # Check if already processed (duplicate detection)
        if email in self.processed_emails:
            result['reason'] = 'Duplicate email - using cached result'
            return result
        
        self.processed_emails.add(email)

        # Step 1: Format validation (early exit)
        if not self.is_valid_format(email):
            result['reason'] = 'Invalid email format'
            if self.progress_tracker:
                self.progress_tracker.mark_processed(email)
            return result

        result['format_valid'] = True

        try:
            domain = email.split('@')[1].lower()

            # Anti-spam rate limiting
            if not self._check_rate_limit(domain):
                result['reason'] = 'Rate limit exceeded for domain (anti-spam)'
                return result

            # Step 2: Get MX record (early exit)
            mx_record = self.get_mx_record(domain)
            if not mx_record:
                result['reason'] = 'No MX record found'
                if self.progress_tracker:
                    self.progress_tracker.mark_processed(email)
                return result

            result['domain_exists'] = True

            # Step 3: SMTP verification (skip if configured)
            if self.skip_smtp:
                result['valid'] = True
                result['reason'] = 'Format and domain valid (SMTP skipped)'
                if self.progress_tracker:
                    self.progress_tracker.mark_processed(email)
                return result

            # Anti-spam measures: randomize connection parameters
            helo_domain = random.choice(self.helo_domains) if self.anti_spam_mode else 'gmail.com'
            sender_email = random.choice(self.sender_emails) if self.anti_spam_mode else 'test@gmail.com'

            try:
                server = smtplib.SMTP(timeout=self.timeout)
                server.set_debuglevel(0)
                server.connect(mx_record, 25)
                server.helo(helo_domain)
                server.mail(sender_email)
                code, message = server.rcpt(email)
                server.quit()

                if code == 250:
                    result['valid'] = True
                    result['smtp_valid'] = True
                    result['reason'] = 'Email verified successfully'
                    self.domain_error_counts[domain] = 0
                else:
                    result['reason'] = f'SMTP rejected: {code} {message}'
                    self._handle_domain_error(domain)

            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPServerDisconnected, socket.timeout) as e:
                result['reason'] = f'SMTP error: {type(e).__name__}'
                self._handle_domain_error(domain)
            except Exception as e:
                result['reason'] = f'SMTP error: {str(e)}'
                self._handle_domain_error(domain)

        except Exception as e:
            result['reason'] = f'General error: {str(e)}'

        # Mark as processed in progress tracker
        if self.progress_tracker:
            self.progress_tracker.mark_processed(email)

        return result

    def _handle_domain_error(self, domain: str):
        """Handle domain-specific errors and adjust delays"""
        self.domain_error_counts[domain] += 1
        if self.domain_error_counts[domain] > 3:
            # Exponential backoff for problematic domains
            self.domain_delays[domain] = min(self.domain_delays[domain] * 1.5, 10.0)
            logger.debug(f"Increased delay for {domain} to {self.domain_delays[domain]:.1f}s")

    def get_domain_delay(self, email: str) -> float:
        """Get domain-specific delay"""
        domain = email.split('@')[1].lower()
        return self.domain_delays[domain]


async def validate_email_batch(validator: EmailValidator, emails_batch: List[Tuple[int, Dict]], 
                               csv_writer: StreamingCSVWriter, fieldnames: List[str]) -> Tuple[int, int]:
    """Validate a batch of emails concurrently with streaming output"""
    valid_count = 0
    invalid_count = 0
    
    async def validate_single(email_data):
        nonlocal valid_count, invalid_count
        
        i, row = email_data
        email = row['email'].strip().lower()
        
        # Skip if already processed (resume capability)
        if validator.progress_tracker and validator.progress_tracker.is_processed(email):
            logger.info(f"Skipped {i}: {email} - Already processed")
            return
        
        # Use domain-specific delay with anti-spam jitter
        domain_delay = validator.get_domain_delay(email)
        if validator.anti_spam_mode:
            jitter = random.uniform(0.1, 0.5)
            domain_delay += jitter
        await asyncio.sleep(domain_delay)
        
        # Run sync validation in thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            validation_result = await loop.run_in_executor(
                executor, validator.verify_email_smtp, email
            )
        
        row_with_validation = row.copy()
        row_with_validation.update({
            'email_original': row['email'],
            'email': email,
            'email_valid': validation_result['valid'],
            'validation_reason': validation_result['reason'],
            'format_valid': validation_result['format_valid'],
            'domain_exists': validation_result['domain_exists'],
            'smtp_valid': validation_result['smtp_valid']
        })
        
        # Stream write immediately
        csv_writer.write_result(row_with_validation, fieldnames)
        
        # Update counters
        if validation_result['valid']:
            valid_count += 1
        else:
            invalid_count += 1
            
        status = "✓ Valid" if validation_result['valid'] else f"✗ Invalid - {validation_result['reason']}"
        logger.info(f"Processed {i}: {email} - {status}")
        
        # Save progress periodically
        if validator.progress_tracker and (valid_count + invalid_count) % 50 == 0:
            validator.progress_tracker.save_progress()
    
    # Process batch concurrently
    tasks = [validate_single(email_data) for email_data in emails_batch]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return valid_count, invalid_count

async def process_csv_file_async(input_file: str, output_file: str, delay: float = 1.5, 
                                max_workers: int = 20, skip_smtp: bool = False, 
                                anti_spam_mode: bool = True, resume: bool = True):
    """
    Process CSV file with streaming output, resume capability, and anti-spam measures
    """
    # Setup progress tracking
    progress_file = f"{input_file}.progress"
    progress_tracker = ProgressTracker(progress_file) if resume else None
    
    # Setup validator with anti-spam measures
    validator = EmailValidator(
        delay=delay, 
        max_workers=max_workers, 
        skip_smtp=skip_smtp,
        anti_spam_mode=anti_spam_mode,
        progress_tracker=progress_tracker
    )
    
    # Setup streaming CSV writer
    csv_writer = StreamingCSVWriter(output_file)
    
    total_valid = 0
    total_invalid = 0
    
    try:
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            total_rows = len(rows)
            
            # Get fieldnames for CSV output
            if rows:
                sample_result = {
                    **rows[0],
                    'email_original': '',
                    'email': '',
                    'email_valid': False,
                    'validation_reason': '',
                    'format_valid': False,
                    'domain_exists': False,
                    'smtp_valid': False
                }
                fieldnames = list(sample_result.keys())
            else:
                logger.error("No data found in input file")
                return
            
            # Count already processed emails for resume
            already_processed = 0
            if progress_tracker:
                already_processed = len([r for r in rows if progress_tracker.is_processed(r['email'].strip().lower())])
            
            remaining = total_rows - already_processed
            logger.info(f"Processing {remaining}/{total_rows} emails (resume: {resume}, anti-spam: {anti_spam_mode})")
            logger.info(f"Max workers: {max_workers}, Skip SMTP: {skip_smtp}")
            
            # Process in batches to control concurrency
            batch_size = max_workers
            for i in range(0, total_rows, batch_size):
                batch = [(j + 1, rows[j]) for j in range(i, min(i + batch_size, total_rows))]
                
                batch_num = i//batch_size + 1
                total_batches = (total_rows + batch_size - 1)//batch_size
                logger.info(f"Processing batch {batch_num}/{total_batches}")
                
                batch_valid, batch_invalid = await validate_email_batch(
                    validator, batch, csv_writer, fieldnames
                )
                
                total_valid += batch_valid
                total_invalid += batch_invalid
                
                # Save progress after each batch
                if progress_tracker:
                    progress_tracker.save_progress()
    
    except FileNotFoundError:
        logger.error(f"Input file '{input_file}' not found")
        return
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        return
    finally:
        # Final progress save
        if progress_tracker:
            progress_tracker.save_progress()
    
    # Print summary
    total_processed = total_valid + total_invalid
    if total_processed == 0:
        logger.warning("No emails were processed.")
        return
        
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"Total emails processed this session: {total_processed}")
    logger.info(f"Valid emails: {total_valid} ({total_valid / total_processed * 100:.1f}%)")
    logger.info(f"Invalid emails: {total_invalid} ({total_invalid / total_processed * 100:.1f}%)")
    logger.info(f"Results written to:")
    logger.info(f"  - Valid: {csv_writer.valid_filename}")
    logger.info(f"  - Invalid: {csv_writer.invalid_filename}")
    logger.info(f"  - Combined: {csv_writer.results_filename}")
    
    # Clean up progress file if completed
    if resume and total_processed > 0:
        logger.info(f"Progress saved to: {progress_file} (delete to restart from beginning)")

def process_csv_file(input_file: str, output_file: str, delay: float = 1.5, 
                    max_workers: int = 20, skip_smtp: bool = False, 
                    anti_spam_mode: bool = True, resume: bool = True):
    """
    Wrapper for async processing with all new features
    """
    asyncio.run(process_csv_file_async(
        input_file, output_file, delay, max_workers, skip_smtp, anti_spam_mode, resume
    ))


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
    """Main function with streaming output, resume, and anti-spam features"""
    if len(sys.argv) < 2:
        print("Usage: email-validation <input_file.csv> [output_file.csv] [delay_seconds] [max_workers] [flags]")
        print("Flags: --skip-smtp, --no-anti-spam, --no-resume")
        print("Examples:")
        print("  email-validation emails.csv results.csv 1.0 50")
        print("  email-validation emails.csv results.csv 0.5 30 --skip-smtp")
        print("  email-validation huge_list.csv results.csv 0.2 100 --no-anti-spam")
        print("  email-validation emails.csv results.csv 1.0 20 --no-resume")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'cleaned_emails.csv'
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    max_workers = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    
    # Parse flags
    skip_smtp = '--skip-smtp' in sys.argv
    anti_spam_mode = '--no-anti-spam' not in sys.argv
    resume = '--no-resume' not in sys.argv

    logger.info(f"Input file: {input_file}")
    logger.info(f"Output base: {output_file}")
    logger.info(f"Delay between checks: {delay} seconds")
    logger.info(f"Max concurrent workers: {max_workers}")
    logger.info(f"Skip SMTP verification: {skip_smtp}")
    logger.info(f"Anti-spam mode: {anti_spam_mode}")
    logger.info(f"Resume capability: {resume}")

    process_csv_file(input_file, output_file, delay, max_workers, skip_smtp, anti_spam_mode, resume)


if __name__ == "__main__":
    main()