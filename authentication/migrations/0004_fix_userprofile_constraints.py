# Manual migration to fix UserProfile database constraints

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_userprofile_verified'),
    ]

    operations = [
        # Make sure verified field has proper default
        migrations.RunSQL(
            "ALTER TABLE user_profile ALTER COLUMN verified SET DEFAULT false;",
            reverse_sql="ALTER TABLE user_profile ALTER COLUMN verified DROP DEFAULT;"
        ),
        
        # Add phone field if it doesn't exist
        migrations.RunSQL(
            "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS phone VARCHAR(20);",
            reverse_sql="ALTER TABLE user_profile DROP COLUMN IF EXISTS phone;"
        ),
        
        # Make sure all nullable boolean fields have proper defaults
        migrations.RunSQL(
            """
            UPDATE user_profile SET 
                email_notifications = COALESCE(email_notifications, true),
                push_notifications = COALESCE(push_notifications, true),
                newsletter_subscription = COALESCE(newsletter_subscription, false),
                is_verified = COALESCE(is_verified, false),
                is_premium = COALESCE(is_premium, false),
                google_connected = COALESCE(google_connected, false),
                twitter_connected = COALESCE(twitter_connected, false),
                telegram_connected = COALESCE(telegram_connected, false),
                login_count = COALESCE(login_count, 0),
                verified = COALESCE(verified, false)
            WHERE verified IS NULL OR email_notifications IS NULL OR push_notifications IS NULL 
            OR newsletter_subscription IS NULL OR is_verified IS NULL OR is_premium IS NULL
            OR google_connected IS NULL OR twitter_connected IS NULL OR telegram_connected IS NULL
            OR login_count IS NULL;
            """,
            reverse_sql="-- No reverse needed"
        ),
    ]