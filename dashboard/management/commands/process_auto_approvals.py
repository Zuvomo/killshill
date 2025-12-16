"""
Management command to process auto-approvals for pending influencer submissions
"""

import asyncio
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

from dashboard.services.auto_approval import auto_approval_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending influencer submissions for auto-approval'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Maximum number of submissions to process in one run'
        )
        
        parser.add_argument(
            '--submission-id',
            type=int,
            help='Process specific submission ID'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate processing without making changes'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        if options['verbose']:
            logging.basicConfig(level=logging.INFO)
        
        limit = options['limit']
        submission_id = options.get('submission_id')
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('Running in DRY RUN mode - no changes will be made')
            )
        
        # Run async processing
        if submission_id:
            results = asyncio.run(self._process_single_submission(submission_id, dry_run))
        else:
            results = asyncio.run(self._process_multiple_submissions(limit, dry_run))
        
        # Display results
        self._display_results(results)
    
    async def _process_single_submission(self, submission_id: int, dry_run: bool) -> dict:
        """Process single submission"""
        self.stdout.write(f'Processing submission ID: {submission_id}')
        
        if dry_run:
            # In dry run, use sync_to_async to avoid context issues
            from asgiref.sync import sync_to_async
            from dashboard.models import InfluencerSubmission
            
            @sync_to_async
            def get_submission():
                try:
                    return InfluencerSubmission.objects.get(id=submission_id)
                except InfluencerSubmission.DoesNotExist:
                    return None
            
            submission = await get_submission()
            
            if submission:
                return {
                    'processed': 1,
                    'approved': 0,
                    'rejected': 0,
                    'results': [{
                        'submission_id': submission_id,
                        'channel_name': submission.channel_name,
                        'success': True,
                        'dry_run': True
                    }]
                }
            else:
                return {
                    'processed': 0,
                    'approved': 0,
                    'rejected': 0,
                    'results': [{
                        'submission_id': submission_id,
                        'success': False,
                        'error': 'Submission not found'
                    }]
                }
        
        result = await auto_approval_service.process_submission(submission_id)
        return {
            'processed': 1,
            'approved': 1 if result.get('approved') else 0,
            'rejected': 1 if result.get('success') and not result.get('approved') else 0,
            'results': [result]
        }
    
    async def _process_multiple_submissions(self, limit: int, dry_run: bool) -> dict:
        """Process multiple submissions"""
        self.stdout.write(f'Processing up to {limit} pending submissions...')
        
        if dry_run:
            # In dry run, use sync_to_async to avoid context issues
            from django.db import models
            from asgiref.sync import sync_to_async
            from dashboard.models import InfluencerSubmission
            
            @sync_to_async
            def get_pending_count():
                return InfluencerSubmission.objects.filter(status='pending').count()
            
            pending_count = await get_pending_count()
            actual_limit = min(pending_count, limit)
            
            return {
                'processed': actual_limit,
                'approved': 0,
                'rejected': 0,
                'results': [{
                    'dry_run': True,
                    'message': f'Would process {actual_limit} submissions'
                }]
            }
        
        return await auto_approval_service.process_pending_submissions(limit)
    
    def _display_results(self, results: dict):
        """Display processing results"""
        processed = results['processed']
        approved = results['approved']
        rejected = results['rejected']
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Processing Results ==='))
        self.stdout.write(f'Processed: {processed}')
        self.stdout.write(f'Approved: {self.style.SUCCESS(str(approved))}')
        self.stdout.write(f'Rejected: {self.style.ERROR(str(rejected))}')
        self.stdout.write(f'Pending Review: {processed - approved - rejected}')
        
        if results.get('results'):
            self.stdout.write('')
            self.stdout.write('=== Detailed Results ===')
            
            for result in results['results']:
                submission_id = result.get('submission_id', 'N/A')
                channel_name = result.get('channel_name', 'N/A')
                
                if result.get('dry_run'):
                    status = self.style.WARNING('DRY RUN')
                    message = result.get('message', '')
                elif result.get('success'):
                    if result.get('approved'):
                        status = self.style.SUCCESS('APPROVED')
                        score = result.get('approval_score', 0)
                        confidence = result.get('confidence_score', 0)
                        message = f'Score: {score}, Confidence: {confidence}'
                    else:
                        status = self.style.WARNING('PENDING REVIEW')
                        score = result.get('approval_score', 0)
                        message = f'Score: {score} (below threshold)'
                else:
                    status = self.style.ERROR('FAILED')
                    message = result.get('error', 'Unknown error')
                
                self.stdout.write(
                    f'ID: {submission_id} | {channel_name} | {status} | {message}'
                )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Processing complete!'))