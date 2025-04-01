from flask_login import UserMixin
from bson import ObjectId
from datetime import datetime

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.cooking_methods = user_data.get('cooking_methods', [])
        self.kitchen_tools = user_data.get('kitchen_tools', [])
        self.preferences = user_data.get('preferences', {})

    @staticmethod
    def get(user_id, mongo):
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        return User(user_data) if user_data else None

class InventoryItem:
    def __init__(self, item_data):
        self.id = str(item_data['_id'])
        self.name = item_data['name']
        self.quantity = item_data['quantity']
        self.unit = item_data['unit']
        self.expiry_date = item_data.get('expiry_date')
        self.user_id = item_data['user_id']
        self.date_added = item_data.get('date_added', datetime.utcnow())

class Receipt:
    def __init__(self, receipt_data):
        self.id = str(receipt_data['_id'])
        self.filename = receipt_data['filename']
        self.upload_date = receipt_data.get('upload_date', datetime.utcnow())
        self.processed_date = receipt_data.get('processed_date')
        self.user_id = receipt_data['user_id']
        self.items = receipt_data.get('items', [])

class Recipe:
    def __init__(self, recipe_data):
        self.id = str(recipe_data['_id'])
        self.name = recipe_data['name']
        self.ingredients = recipe_data['ingredients']
        self.instructions = recipe_data['instructions']
        self.prep_time = recipe_data.get('prep_time')
        self.cook_time = recipe_data.get('cook_time')
        self.servings = recipe_data.get('servings')
        self.difficulty = recipe_data.get('difficulty')
        self.created_by = recipe_data.get('created_by')
        self.created_at = recipe_data.get('created_at', datetime.utcnow())

class RecipeRating:
    def __init__(self, rating_data):
        self.id = str(rating_data['_id'])
        self.recipe_name = rating_data['recipe_name']
        self.user_id = rating_data['user_id']
        self.rating = rating_data['rating']
        self.created_at = rating_data.get('created_at', datetime.utcnow())

class ChatMessage:
    def __init__(self, message_data):
        self.id = str(message_data['_id'])
        self.user_id = message_data['user_id']
        self.message = message_data['message']
        self.response = message_data['response']
        self.created_at = message_data.get('created_at', datetime.utcnow()) 