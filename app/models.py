from app import db

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    ingredients = db.Column(db.Text, nullable=False) # Could be JSON or a separate table
    instructions = db.Column(db.Text, nullable=False)
    # user_id = db.Column(db.Integer, db.ForeignKey('user.id')) # Assuming a User model

    def __repr__(self):
        return f'<Recipe {self.name}>'

# Example User model (if you were to create users)
# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(64), index=True, unique=True)
#     recipes = db.relationship('Recipe', backref='author', lazy='dynamic')
#
#     def __repr__(self):
#         return f'<User {self.username}>'
