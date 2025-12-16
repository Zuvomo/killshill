# Killshill - Influencer Credibility Platform

A comprehensive Django application for tracking and analyzing influencer trading performance with AI-verified results.

## Features

- **Multi-Platform Authentication**: Google, Twitter, Telegram OAuth + JWT
- **KOL Leaderboard**: Real-time influencer rankings with accuracy metrics
- **AI-Verified Results**: Automated trade call analysis and verification
- **Admin Console**: Comprehensive management interface
- **RESTful API**: Complete API for frontend integration
- **Data Validation**: Advanced deduplication and quality checks
- **Supabase Integration**: PostgreSQL database with existing table support

## Architecture

### Apps Structure
- **authentication**: User management, OAuth, JWT tokens, social login
- **influencers**: Core models (Influencer, TradeCall, Asset) with Supabase integration
- **dashboard**: UI views and templates for main interface
- **api**: RESTful API endpoints with auto-approval logic

### Key Models
- **Influencer**: Tracks social media influencers/traders
- **TradeCall**: Individual trading signals with performance metrics
- **Asset**: Financial instruments (crypto, stocks, forex)
- **UserProfile**: Extended user data with social account linking

## Quick Start

1. **Clone and Setup**
   ```bash
   cd killshill-project
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   Copy `.env` file and update with your credentials:
   ```
   # Database (Supabase)
   DB_USER=postgres.wasgbfsurcyzsqbikabf
   DB_PASSWORD=Zuvomo@killshill007
   DB_HOST=aws-1-ap-south-1.pooler.supabase.com
   DB_PORT=6543
   
   # OAuth Keys
   GOOGLE_OAUTH2_CLIENT_ID=your-google-client-id
   TWITTER_OAUTH2_CLIENT_ID=your-twitter-client-id
   TELEGRAM_BOT_TOKEN=your-telegram-bot-token
   ```

3. **Database Setup**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

## API Endpoints

### Authentication
- `POST /auth/api/register/` - User registration
- `POST /auth/api/login/` - Login with JWT token
- `GET /auth/api/profile/` - Get user profile
- `POST /auth/api/logout/` - Logout and blacklist token

### Main API
- `GET /api/v1/leaderboard/` - KOL leaderboard with filters
- `GET /api/v1/trending-kols/` - Trending KOLs by category
- `GET /api/v1/top-signals/` - Recent top signals
- `POST /api/v1/submit-influencer/` - Submit influencer for approval
- `GET /api/v1/search-influencers/` - Search influencers
- `GET /api/v1/analytics/` - Analytics dashboard data

### OAuth URLs
- `/accounts/google/login/` - Google OAuth
- `/accounts/twitter_oauth2/login/` - Twitter OAuth
- `/auth/telegram/` - Telegram authentication

## Dashboard Features

### Main Views
- **Dashboard**: Overview with stats and recent activity
- **Leaderboard**: Sortable KOL rankings with filters
- **Trending KOLs**: Category-wise trending analysis
- **Analytics**: Advanced consensus and performance metrics
- **Search**: Influencer search with platform filters

### Admin Features
- **Influencer Management**: Add, edit, approve influencers
- **Trade Call Analysis**: View and verify trading signals
- **Asset Management**: Manage trading assets
- **User Administration**: User profiles and permissions

## Data Validation & Quality

### Auto-Approval Logic
- Followers > 1,000: Auto-approve
- Verified social platforms: Auto-approve
- Manual review for others

### Deduplication
- URL-based duplicate detection
- Platform + username matching
- Similar name detection with merge capability

### Data Validation
- Platform URL validation
- Trade call data structure validation
- Asset symbol format validation
- Follower count reasonableness checks

## Security Features

- JWT token authentication with refresh
- Session tracking and management
- CORS protection
- SQL injection prevention
- XSS protection via Django templates

## Performance Optimization

- Database indexing on key fields
- Query optimization with select_related
- Pagination for large datasets
- API response caching ready

## Production Deployment

1. **Environment Setup**
   ```bash
   DEBUG=False
   ALLOWED_HOSTS=your-domain.com
   SECRET_KEY=your-production-secret-key
   ```

2. **Static Files**
   ```bash
   python manage.py collectstatic
   ```

3. **Database Migration**
   ```bash
   python manage.py migrate
   ```

4. **Gunicorn Setup**
   ```bash
   gunicorn killshill.wsgi:application
   ```

## Integration Notes

### Existing Supabase Tables
- Models use `managed = False` to work with existing tables
- Foreign key relationships maintained
- Custom primary keys preserved (`influencer_id`, etc.)

### Frontend Integration
- RESTful API ready for React/Vue/Angular
- JWT authentication flow implemented
- CORS configured for development

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request with clear description

## License

MIT License - See LICENSE file for details