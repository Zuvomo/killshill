from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings


class Command(BaseCommand):
    help = 'Setup social authentication applications'

    def handle(self, *args, **options):
        # Update site configuration
        site = Site.objects.get(pk=settings.SITE_ID)
        site.domain = 'localhost:8000'
        site.name = 'KillShill Development'
        site.save()
        self.stdout.write(
            self.style.SUCCESS(f'Updated site: {site.domain}')
        )

        # Get Google OAuth credentials from settings
        google_client_id = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {}).get('APP', {}).get('client_id')
        google_client_secret = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {}).get('APP', {}).get('secret')

        # Create Google social app if credentials are available
        if google_client_id and google_client_secret:
            google_app, created = SocialApp.objects.get_or_create(
                provider='google',
                defaults={
                    'name': 'Google OAuth',
                    'client_id': google_client_id,
                    'secret': google_client_secret,
                }
            )
            if not created:
                google_app.client_id = google_client_id
                google_app.secret = google_client_secret
                google_app.save()
            
            google_app.sites.add(site)
            self.stdout.write(
                self.style.SUCCESS(f'{"Created" if created else "Updated"} Google OAuth app')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Google OAuth credentials not found in settings. Please set GOOGLE_OAUTH2_CLIENT_ID and GOOGLE_OAUTH2_CLIENT_SECRET in your .env file')
            )

        # Get Twitter OAuth credentials
        twitter_client_id = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('twitter_oauth2', {}).get('APP', {}).get('client_id')
        twitter_client_secret = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('twitter_oauth2', {}).get('APP', {}).get('secret')

        # Create Twitter social app if credentials are available
        if twitter_client_id and twitter_client_secret:
            twitter_app, created = SocialApp.objects.get_or_create(
                provider='twitter_oauth2',
                defaults={
                    'name': 'Twitter OAuth2',
                    'client_id': twitter_client_id,
                    'secret': twitter_client_secret,
                }
            )
            if not created:
                twitter_app.client_id = twitter_client_id
                twitter_app.secret = twitter_client_secret
                twitter_app.save()
            
            twitter_app.sites.add(site)
            self.stdout.write(
                self.style.SUCCESS(f'{"Created" if created else "Updated"} Twitter OAuth2 app')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Twitter OAuth2 credentials not found in settings. Please set TWITTER_OAUTH2_CLIENT_ID and TWITTER_OAUTH2_CLIENT_SECRET in your .env file')
            )

        self.stdout.write(
            self.style.SUCCESS('Social authentication setup complete!')
        )
        self.stdout.write(
            self.style.SUCCESS('Now you can test Google and Twitter login at /auth/login/')
        )