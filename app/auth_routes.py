from flask import Blueprint, redirect, url_for, current_app, flash
from flask_dance.contrib.google import make_google_blueprint
from flask_dance.consumer import oauth_authorized, oauth_error
from flask_login import login_user, logout_user
# Assuming 'db' and 'User' are accessible from '.models' relative to 'app' directory
# If app factory pattern is used, db might be imported differently or accessed via current_app.
from .models import db, User
from . import login_manager # To potentially refresh user or for other login_manager uses

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/auth')

# Note: client_id and client_secret are fetched from current_app.config
# This means the blueprint must be registered *after* the app config is loaded.
google_bp = make_google_blueprint(
    # client_id and client_secret are typically loaded from current_app.config by Flask-Dance
    # if not explicitly passed here. For clarity, ensure app.config is populated before this blueprint is registered.
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to='auth_bp.google_auth_authorized_callback',
    # offline=True, # Enable to get refresh tokens
    # reprompt_consent=True, # Useful for dev
)
auth_bp.register_blueprint(google_bp, url_prefix="/google_login") # Ensure this line is present and correct

@oauth_authorized.connect_via(google_bp)
def google_auth_authorized_callback(blueprint, token): # Renamed for clarity
    if not token:
        flash("Failed to log in with Google. Token not received.", "error")
        return redirect(url_for('routes.index'))

    resp = blueprint.session.get("/oauth2/v3/userinfo") # blueprint.session is an OAuth2Session
    if not resp.ok:
        flash("Failed to fetch user information from Google.", "error")
        return redirect(url_for('routes.index'))

    user_info = resp.json()
    google_id = str(user_info.get("sub"))
    email = user_info.get("email")
    name = user_info.get("name")
    profile_pic = user_info.get("picture")

    if not email: # Email is crucial for our User model
        flash("Email not provided by Google. Cannot log in.", "error")
        return redirect(url_for('routes.index'))


    # Find or create user in database
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        # If no user by google_id, check if an account with that email already exists
        user = User.query.filter_by(email=email).first()
        if not user: # Truly new user
            user = User(google_id=google_id, email=email, name=name, profile_pic_url=profile_pic)
            db.session.add(user)
        else: # Existing user by email, link google_id and update info potentially
            user.google_id = google_id
            if name: user.name = name # Update name if Google provides it
            if profile_pic: user.profile_pic_url = profile_pic # Update pic if Google provides it
    else: # User found by google_id, update info
        user.email = email # Email might change or be more accurate via Google
        if name: user.name = name
        if profile_pic: user.profile_pic_url = profile_pic

    try:
        db.session.commit()
        login_user(user)
        flash("Successfully logged in with Google!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error during login process: {str(e)}", "error")
        current_app.logger.error(f"Database error in google_auth_authorized_callback: {e}")
        return redirect(url_for('index')) # Main index route

    return redirect(url_for('profile')) # Main profile route

@oauth_error.connect_via(google_bp)
def google_oauth_error_handler(blueprint, message, error=None, error_description=None, error_uri=None): # Updated signature
    # Log the error
    # The 'message' parameter in newer Flask-Dance versions might be the primary error message.
    # 'error', 'error_description' might come from the OAuth provider in the URL.
    log_message = f"OAuth error from {blueprint.name}: {message}"
    if error: log_message += f", Error: {error}"
    if error_description: log_message += f", Description: {error_description}"
    if error_uri: log_message += f", URI: {error_uri}"
    current_app.logger.error(log_message)

    flash(f"OAuth error: {message or error_description or error}", "error")
    return redirect(url_for('index')) # Main index route

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index')) # Main index route

# Need to register this blueprint with the main app instance in __init__.py
# And also google_bp needs to be registered with auth_bp or directly with app.
# For modularity, auth_bp registers google_bp.
# The main app registers auth_bp (this happens in app/__init__.py)
