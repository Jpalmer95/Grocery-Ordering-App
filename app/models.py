from app import db
from flask_login import UserMixin

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    ingredients = db.Column(db.Text, nullable=False) # Could be JSON or a separate table
    instructions = db.Column(db.Text, nullable=False)
    # user_id = db.Column(db.Integer, db.ForeignKey('user.id')) # Assuming a User model

    def __repr__(self):
        return f'<Recipe {self.name}>'

class UserSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Still useful as a PK for the table itself
    hugging_face_api_key = db.Column(db.String(200), nullable=True)
    gemini_api_key = db.Column(db.String(200), nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    user = db.relationship('User', backref=db.backref('settings', uselist=False, lazy='joined'))
    theme = db.Column(db.String(10), default='light', nullable=False)
    dietary_restrictions = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<UserSettings for User {self.user_id} - Theme: {self.theme} - Restrictions: {self.dietary_restrictions[:30] if self.dietary_restrictions else "None"}>'

# login_manager import and user_loader will be moved to __init__.py or an auth module

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    profile_pic_url = db.Column(db.String(255), nullable=True)
    # is_active by default is True from UserMixin

    def __repr__(self):
        return f'<User {self.email}>'

# user_loader moved to __init__.py

# The commented out User model example below can be removed or kept for reference.
# For now, I will remove it to avoid confusion with the new User model.
