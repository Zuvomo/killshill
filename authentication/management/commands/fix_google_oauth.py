from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix Google OAuth configuration by ensuring clean setup'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Delete ALL social apps to start fresh
            deleted_count = SocialApp.objects.all().count()
            SocialApp.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} existing social apps')

            # Get current site
            site = Site.objects.get(pk=settings.SITE_ID)
            site.domain = 'localhost:8000'
            site.name = 'KillShill Development'
            site.save()
            self.stdout.write(f'Updated site: {site.domain}')

            # Get Google OAuth credentials
            google_client_id = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}).get('client_id')
            google_client_secret = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}).get('secret')

            if google_client_id and google_client_secret:
                # Create single Google social app
                google_app = SocialApp.objects.create(
                    provider='google',
                    name='Google OAuth',
                    client_id=google_client_id,
                    secret=google_client_secret,
                )
                google_app.sites.add(site)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created Google OAuth app (ID: {google_app.id})')
                )
                
                # Verify the setup
                google_apps = SocialApp.objects.filter(provider='google')
                self.stdout.write(f'Google apps in database: {google_apps.count()}')
                
                if google_apps.count() == 1:
                    app = google_apps.first()
                    self.stdout.write(f'✅ Verification passed:')
                    self.stdout.write(f'   - App ID: {app.id}')
                    self.stdout.write(f'   - Provider: {app.provider}')
                    self.stdout.write(f'   - Client ID: {app.client_id[:20]}...')
                    self.stdout.write(f'   - Secret set: {bool(app.secret)}')
                    self.stdout.write(f'   - Sites: {list(app.sites.all())}')
                else:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Expected 1 Google app, found {google_apps.count()}')
                    )
            else:
                self.stdout.write(
                    self.style.WARNING('❌ Google OAuth credentials not found in settings')
                )
                self.stdout.write('Please ensure GOOGLE_OAUTH2_CLIENT_ID and GOOGLE_OAUTH2_CLIENT_SECRET are set in your .env file')

            # Optional: Create Twitter app if credentials exist
            twitter_client_id = settings.SOCIALACCOUNT_PROVIDERS.get('twitter_oauth2', {}).get('APP', {}).get('client_id')
            twitter_client_secret = settings.SOCIALACCOUNT_PROVIDERS.get('twitter_oauth2', {}).get('APP', {}).get('secret')

            if twitter_client_id and twitter_client_secret and twitter_client_id != 'your-twitter-client-id':
                twitter_app = SocialApp.objects.create(
                    provider='twitter_oauth2',
                    name='Twitter OAuth2',
                    client_id=twitter_client_id,
                    secret=twitter_client_secret,
                )
                twitter_app.sites.add(site)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created Twitter OAuth2 app (ID: {twitter_app.id})')
                )

            self.stdout.write(
                self.style.SUCCESS('\n🎉 OAuth setup complete!')
            )
            self.stdout.write('Test Google OAuth at: http://localhost:8000/accounts/google/login/')