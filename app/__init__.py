from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

app = Flask(__name__)
from .config import Config # Import the Config class
app.config.from_object(Config) # Load config from Config class

# Update SQLALCHEMY_DATABASE_URI to also come from config or use a default
app.config.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///app.db')
app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

from app import routes, models # Import models here
from app.llm_service import init_llm_client

# Initialize LLM client
init_llm_client(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
# The login view for google_bp (named 'google' by default from make_google_blueprint)
# registered under auth_bp will be 'auth_bp.google.login'
login_manager.login_view = 'auth_bp.google.login'

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    # Ensure models are imported before this is called, or move User import here
    from app.models import User
    return User.query.get(int(user_id))

# Import and register blueprints
from .auth_routes import auth_bp
app.register_blueprint(auth_bp)

@app.context_processor
def utility_processor():
    from flask_login import current_user # Import current_user here
    def get_current_theme():
        if current_user.is_authenticated and hasattr(current_user, 'settings') and current_user.settings:
            return current_user.settings.theme
        return 'system' # Default if no user, no settings, or no theme set on settings
    return dict(get_current_theme=get_current_theme)

# It's common to also register the specific OAuth blueprint (google_bp) if it's not nested,
# but since google_bp is registered with auth_bp, registering auth_bp is sufficient.
# from .auth_routes import google_bp
# app.register_blueprint(google_bp, url_prefix="/login") # Example if not nested
