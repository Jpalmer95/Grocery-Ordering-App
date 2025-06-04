import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_super_secret_default_key_for_dev_only' # Should be strong and from env

    # Google OAuth Credentials - Replace with your actual credentials
    # For development, you can set them directly here or use environment variables.
    # For production, ALWAYS use environment variables or a secrets management system.
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID') or 'YOUR_GOOGLE_CLIENT_ID_HERE'
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET') or 'YOUR_GOOGLE_CLIENT_SECRET_HERE'

    # Ensure these are set if you are running behind a proxy or in a container
    # OAUTHLIB_INSECURE_TRANSPORT = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT') or '0' # Set to '1' for http development
    # os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # If testing locally with http callbacks
    # os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1' # If scopes differ slightly

    # Example for setting OAUTHLIB_INSECURE_TRANSPORT for local http development:
    # if os.environ.get('FLASK_ENV') == 'development' and not GOOGLE_OAUTH_CLIENT_ID.startswith('YOUR'):
    #     os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# To use this config:
# from app.config import Config
# app.config.from_object(Config)
