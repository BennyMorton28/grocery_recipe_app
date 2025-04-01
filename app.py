from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import pytesseract
from PIL import Image
from dateutil import parser
import re
from dotenv import load_dotenv
from openai import OpenAI
import json
from flask_pymongo import PyMongo
from bson import ObjectId
from models import User, InventoryItem, Receipt, Recipe, RecipeRating, ChatMessage

# Common grocery item categories and their patterns
GROCERY_CATEGORIES = {
    'coffee': ['folgers', 'maxwell', 'nescafe', 'coffee'],
    'dairy': ['milk', 'cheese', 'yogurt', 'cream', 'butter', 'eggs'],
    'meat': ['chicken', 'chkn', 'beef', 'pork', 'turkey', 'fish', 'salmon'],
    'produce': ['apple', 'banana', 'orange', 'lettuce', 'tomato', 'potato', 'lemon'],
    'beverages': ['juice', 'soda', 'water', 'tea'],
    'snacks': ['chips', 'cookies', 'crackers', 'nuts'],
    'cleaning': ['soap', 'detergent', 'cleaner', 'wipes', 'nitril'],
    'pantry': ['pasta', 'rice', 'flour', 'sugar', 'salt', 'bread', 'pnt buttr', 'peanut butter', 'butter']
}

# Common units mapping
UNIT_PATTERNS = {
    'kg': ['kg', 'kilo', 'kilos', 'kilogram'],
    'g': ['g', 'gram', 'grams'],
    'l': ['l', 'liter', 'liters'],
    'ml': ['ml', 'milliliter'],
    'pcs': ['pc', 'pcs', 'piece', 'pieces', 'count', 'ct', 'pack', 'pkg'],
    'oz': ['oz', 'ounce', 'ounces'],
    'lb': ['lb', 'lbs', 'pound', 'pounds']
}

# Patterns to ignore in receipt processing
IGNORE_PATTERNS = [
    r'^tel:?\s*\+?\d[\d\-\(\) ]+$',  # Phone numbers
    r'^st#.*te#.*tr#',  # Store transaction details
    r'^[\d\-]+$',  # Just numbers or dashes
    r'^\d{2}/\d{2}/\d{2}',  # Dates
    r'^total\b',  # Totals
    r'^subtotal\b',  # Subtotals
    r'^tax\b',  # Tax lines
    r'^change\b',  # Change due
    r'^\$?\d+\.\d{2}$',  # Just prices
    r'^ref #',  # Reference numbers
    r'^account\s*:',  # Account information
    r'^debit\b',  # Debit card info
    r'^credit\b',  # Credit card info
    r'^card\b',  # Card info
    r'^auth\b',  # Authorization
    r'^approved\b',  # Approval
    r'^network\b',  # Network ID
    r'^manager\b',  # Manager info
    r'^store\b',  # Store info
    r'^save money',  # Store slogans
    r'^live better',  # Store slogans
    r'^\d+ [NSEW]\.?\s+\w+\s+(?:st|ave|road|rd|drive|dr|lane|ln|circle|cir|boulevard|blvd)',  # Addresses
    r'^[a-z\s]+,\s*[a-z]{2}\s+\d{5}',  # City, State ZIP
    r'©',  # Copyright symbols
    r'^items\s+sold',  # Items sold count
    r'^tender',  # Tender type
    r'^balance',  # Balance
    r'^payment',  # Payment
    r'^appr code',  # Approval code
    r'^eft\b',  # Electronic funds transfer
]

# Known product codes and their proper names
PRODUCT_NAMES = {
    '007225003712': 'Bread',
    '007874237003': 'Great Value Peanut Butter',
    '007874201510': 'Parmesan Cheese',
    '007874206784': 'Great Value Chunk Chicken',
    '073191913822': 'Nitrile Gloves',
    '002550000377': 'Folgers Coffee',
    '007874222682': 'Twist Up Soda',
    '060538871459': 'Eggs'
}

# Define available cooking methods and tools
COOKING_METHODS = {
    'stovetop': {
        'name': 'Stovetop/Pan',
        'icon': 'fa-fire'
    },
    'oven': {
        'name': 'Oven',
        'icon': 'fa-temperature-high'
    },
    'microwave': {
        'name': 'Microwave',
        'icon': 'fa-square'
    },
    'air_fryer': {
        'name': 'Air Fryer',
        'icon': 'fa-wind'
    },
    'grill': {
        'name': 'Grill',
        'icon': 'fa-fire-alt'
    },
    'slow_cooker': {
        'name': 'Slow Cooker',
        'icon': 'fa-clock'
    }
}

KITCHEN_TOOLS = {
    'mixer': {
        'name': 'Stand/Hand Mixer',
        'icon': 'fa-blender'
    },
    'blender': {
        'name': 'Blender',
        'icon': 'fa-blender'
    },
    'food_processor': {
        'name': 'Food Processor',
        'icon': 'fa-cog'
    },
    'mandolin': {
        'name': 'Mandolin',
        'icon': 'fa-cut'
    },
    'pressure_cooker': {
        'name': 'Pressure Cooker',
        'icon': 'fa-compress'
    },
    'thermometer': {
        'name': 'Kitchen Thermometer',
        'icon': 'fa-thermometer-half'
    },
    'scale': {
        'name': 'Kitchen Scale',
        'icon': 'fa-balance-scale'
    }
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config["MONGO_URI"] = os.getenv("MONGODB_URI")

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize MongoDB
mongo = PyMongo(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI()  # This will automatically use OPENAI_API_KEY from environment

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id, mongo)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def identify_category(item_name):
    """Identify the category of a grocery item based on keywords."""
    item_name = item_name.lower()
    for category, keywords in GROCERY_CATEGORIES.items():
        if any(keyword in item_name for keyword in keywords):
            return category
    return 'other'

def identify_unit(text):
    """Identify the unit from text based on common patterns."""
    text = text.lower()
    for unit, patterns in UNIT_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            return unit
    return 'pcs'  # default unit

def extract_quantity(text):
    """Extract quantity from text."""
    # Look for common quantity patterns
    qty_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:x|X|\*)',  # matches "2 x" or "2.5 X"
        r'(\d+(?:\.\d+)?)\s*(?:pc|pcs|piece|pieces|count|ct)',  # matches quantity with units
        r'(\d+(?:\.\d+)?)\s*(?:kg|g|l|ml|oz|lb|lbs)',  # matches quantity with weight/volume units
        r'^(\d+(?:\.\d+)?)\s'  # matches number at start of string
    ]
    
    for pattern in qty_patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    
    return 1.0  # default quantity

def should_ignore_line(line):
    """Check if a line should be ignored based on patterns."""
    line = line.lower().strip()
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in IGNORE_PATTERNS)

def extract_product_code(text):
    """Extract product code from text and return proper name if known."""
    code_match = re.search(r'(\d{12})', text)
    if code_match:
        code = code_match.group(1)
        return PRODUCT_NAMES.get(code)
    return None

def clean_item_name(text):
    """Clean and normalize item name."""
    # Try to get proper name from product code first
    proper_name = extract_product_code(text)
    if proper_name:
        return proper_name

    # Remove common receipt artifacts
    artifacts = [
        r'\d{12,}',  # Remove product codes
        r'\d+\s*[xX]\s*',  # Remove quantity markers
        r'\$\d+\.\d{2}',  # Remove prices
        r'\b(?:F|N)\b',  # Remove single letter flags
        r'\b(?:pc|pcs|piece|pieces|count|ct)\b',  # Remove unit indicators
        r'\b(?:kg|g|l|ml|oz|lb|lbs)\b',  # Remove weight/volume units
    ]
    
    cleaned = text
    for pattern in artifacts:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Remove multiple spaces and trim
    cleaned = ' '.join(cleaned.split())
    
    return cleaned.strip()

def extract_price(text):
    """Extract price from text."""
    price_match = re.search(r'\$?(\d+\.\d{2})', text)
    return float(price_match.group(1)) if price_match else 0.0

def process_receipt(image_path):
    """Process receipt image and extract items with improved recognition."""
    # Extract text from image using OCR with improved settings
    text = pytesseract.image_to_string(
        Image.open(image_path),
        config='--psm 6'  # Assume uniform block of text
    )
    
    items = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:  # Skip empty or very short lines
            continue
            
        # Skip non-item lines
        if should_ignore_line(line):
            continue
        
        # Try to extract product name
        item_name = clean_item_name(line)
        if not item_name:
            continue
            
        # Skip if the cleaned name is too short or looks like metadata
        if len(item_name) < 3 or item_name.isnumeric():
            continue
        
        # Extract price
        price = extract_price(line)
        
        # Extract quantity (default to 1 if not found)
        quantity = extract_quantity(line) or 1.0
        
        # Determine unit based on item name and quantity
        unit = identify_unit(line)
        
        # Identify category
        category = identify_category(item_name)
        
        # Only add items that have been categorized (excluding 'other')
        if category != 'other':
            items.append({
                'name': item_name.title(),  # Capitalize properly
                'quantity': quantity,
                'unit': unit,
                'price': price,
                'category': category
            })
    
    return items

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if mongo.db.users.find_one({'username': username}):
            flash('Username already exists')
            return redirect(url_for('register'))

        if mongo.db.users.find_one({'email': email}):
            flash('Email already registered')
            return redirect(url_for('register'))

        user_data = {
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(password),
            'cooking_methods': [],
            'kitchen_tools': [],
            'preferences': {}
        }

        result = mongo.db.users.insert_one(user_data)
        user = User.get(result.inserted_id, mongo)
        login_user(user)
        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user_data = mongo.db.users.find_one({'username': username})
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('dashboard'))

        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_data = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    inventory_items = list(mongo.db.inventory.find({'user_id': ObjectId(current_user.id)}))
    receipts = list(mongo.db.receipts.find({'user_id': ObjectId(current_user.id)}))
    return render_template('dashboard.html', user=user_data, inventory=inventory_items, receipts=receipts)

@app.route('/upload_receipt', methods=['POST'])
@login_required
def upload_receipt():
    if 'receipt' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['receipt']
    if file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        receipt_data = {
            'filename': filename,
            'upload_date': datetime.utcnow(),
            'user_id': ObjectId(current_user.id)
        }
        result = mongo.db.receipts.insert_one(receipt_data)
        return jsonify({'status': 'success', 'id': str(result.inserted_id)})

    return jsonify({'error': 'Invalid file'}), 400

@app.route('/add_item', methods=['POST'])
@login_required
def add_item():
    data = request.get_json()
    item_data = {
        'name': data['name'],
        'quantity': float(data['quantity']),
        'unit': data['unit'],
        'user_id': ObjectId(current_user.id),
        'date_added': datetime.utcnow()
    }
    if 'expiry_date' in data:
        item_data['expiry_date'] = datetime.fromisoformat(data['expiry_date'])
    
    result = mongo.db.inventory.insert_one(item_data)
    return jsonify({'status': 'success', 'id': str(result.inserted_id)})

@app.route('/delete_item/<item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    mongo.db.inventory.delete_one({
        '_id': ObjectId(item_id),
        'user_id': ObjectId(current_user.id)
    })
    return jsonify({'status': 'success'})

@app.route('/get_recipes')
@login_required
def get_recipes():
    recipes = list(mongo.db.recipes.find({'created_by': ObjectId(current_user.id)}))
    return jsonify([{
        'id': str(recipe['_id']),
        'name': recipe['name'],
        'ingredients': recipe['ingredients'],
        'instructions': recipe['instructions'],
        'prep_time': recipe.get('prep_time'),
        'cook_time': recipe.get('cook_time'),
        'servings': recipe.get('servings'),
        'difficulty': recipe.get('difficulty')
    } for recipe in recipes])

@app.route('/rate_recipe', methods=['POST'])
@login_required
def rate_recipe():
    data = request.get_json()
    rating_data = {
        'recipe_name': data['recipe_name'],
        'user_id': ObjectId(current_user.id),
        'rating': data['rating'],
        'created_at': datetime.utcnow()
    }
    mongo.db.recipe_ratings.insert_one(rating_data)
    return jsonify({'status': 'success'})

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    message = data.get('message')
    
    # Your existing chat logic here...
    
    chat_data = {
        'user_id': ObjectId(current_user.id),
        'message': message,
        'response': 'Your AI response here',  # Replace with actual AI response
        'created_at': datetime.utcnow()
    }
    mongo.db.chat_messages.insert_one(chat_data)
    return jsonify({'response': chat_data['response']})

@app.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    if request.method == 'POST':
        data = request.get_json()
        mongo.db.users.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'preferences': data}}
        )
        return jsonify({'status': 'success'})
    
    user_data = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    return jsonify(user_data.get('preferences', {}))

if __name__ == '__main__':
    print("Starting server...")
    print("Access the app on your phone using these URLs:")
    print("Local URL: http://127.0.0.1:8080")
    print("Network URL: http://192.168.1.88:8080")
    print("\nMake sure your phone is on the same WiFi network as this computer")
    print("If you can't connect, try these troubleshooting steps:")
    print("1. Check if your Mac's firewall is blocking connections")
    print("2. Try accessing the app using your computer's browser first")
    print("3. Make sure no VPN is active on either device")
    
    with app.app_context():
        db.create_all()
    
    # Enable more detailed logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    app.run(
        debug=True,
        host='0.0.0.0',  # Listen on all available network interfaces
        port=8080,
        threaded=True    # Enable threading for better performance
    ) 