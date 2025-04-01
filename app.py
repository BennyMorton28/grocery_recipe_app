from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
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
from bson.objectid import ObjectId

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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///grocery_recipe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config["MONGO_URI"] = os.getenv("MONGODB_URI")

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic', 'heif'}

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI()  # This will automatically use OPENAI_API_KEY from environment

# Initialize MongoDB
mongo = PyMongo(app)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    cooking_methods = db.Column(db.JSON, default=list)
    kitchen_tools = db.Column(db.JSON, default=list)
    preferences = db.Column(db.JSON)
    inventory = db.relationship('InventoryItem', backref='user', lazy=True)
    receipts = db.relationship('Receipt', backref='user', lazy=True)
    recipe_ratings = db.relationship('RecipeRating', backref='user', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True)

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    expiry_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    items = db.relationship('ReceiptItem', backref='receipt', lazy=True)

class ReceiptItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20))
    price = db.Column(db.Float)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipt.id'), nullable=False)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    ingredients = db.Column(db.JSON, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    prep_time = db.Column(db.Integer)
    cook_time = db.Column(db.Integer)
    servings = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))

class RecipeRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Boolean, nullable=False)  # True for like, False for dislike
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

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
        
        # Check if username or email already exists
        if mongo.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash('Username or email already exists', 'error')
            return redirect(url_for('register'))
        
        # Create new user
        user_data = {
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "cooking_methods": [],
            "kitchen_tools": [],
            "preferences": {},
            "date_created": datetime.utcnow()
        }
        
        mongo.db.users.insert_one(user_data)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = mongo.db.users.find_one({"username": username})
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's inventory and receipts from MongoDB
    inventory = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.get_id())}))
    receipts = list(mongo.db.receipts.find({"user_id": ObjectId(current_user.get_id())}).sort("upload_date", -1))
    return render_template('dashboard.html', inventory=inventory, receipts=receipts)

@app.route('/upload_receipt', methods=['POST'])
@login_required
def upload_receipt():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload an image file.'}), 400
        
        # Save the file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the receipt image
        try:
            items = process_receipt(filepath)
            
            # Save items to inventory
            for item in items:
                inventory_item = InventoryItem(
                    name=item['name'],
                    quantity=item['quantity'],
                    unit=item['unit'],
                    user_id=current_user.id
                )
                db.session.add(inventory_item)
            
            db.session.commit()
            
            # Clean up the uploaded file
            os.remove(filepath)
            
            return jsonify({
                'success': True,
                'message': f'Successfully added {len(items)} items to inventory',
                'items': items
            })
            
        except Exception as e:
            # Clean up the uploaded file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
            app.logger.error(f"Error processing receipt: {str(e)}")
            return jsonify({'success': False, 'error': f'Error processing receipt: {str(e)}'}), 500
            
    except Exception as e:
        app.logger.error(f"Error uploading receipt: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/add_item', methods=['POST'])
@login_required
def add_item():
    data = request.json
    new_item = InventoryItem(
        name=data['name'],
        quantity=data['quantity'],
        unit=data['unit'],
        expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d') if data.get('expiry_date') else None,
        user_id=current_user.id
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify({'message': 'Item added successfully'})

@app.route('/delete_item/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Item deleted successfully'})

@app.route('/get_recipes')
@login_required
def get_recipes():
    try:
        inventory_items = InventoryItem.query.filter_by(user_id=current_user.id).all()
        app.logger.info(f"Found {len(inventory_items)} inventory items")
        
        if not inventory_items:
            app.logger.warning("No inventory items found")
            return jsonify({'recipes': [], 'message': 'No ingredients available'})

        # Get filters from request
        filters = request.args.get('filters', '{}')
        try:
            filters = json.loads(filters)
            app.logger.info(f"Received filters: {filters}")
        except json.JSONDecodeError:
            filters = {}
            app.logger.warning("Failed to parse filters JSON")

        # Format inventory items with clean units
        ingredients_list = []
        ingredients_summary = []
        for item in inventory_items:
            if item.quantity and item.unit:
                formatted_amount = clean_unit(item.quantity, item.unit)
                ingredients_list.append(f"- {formatted_amount} of {item.name}")
                ingredients_summary.append(f"{formatted_amount} of {item.name}")
            else:
                ingredients_list.append(f"- {item.name}")
                ingredients_summary.append(item.name)

        ingredients_text = "\n".join(ingredients_list)
        app.logger.info(f"Formatted ingredients:\n{ingredients_text}")

        # Get user's cooking methods and tools
        cooking_methods = [COOKING_METHODS[method]['name'] for method in (current_user.cooking_methods or []) if method in COOKING_METHODS]
        kitchen_tools = [KITCHEN_TOOLS[tool]['name'] for tool in (current_user.kitchen_tools or []) if tool in KITCHEN_TOOLS]
        
        app.logger.info(f"User cooking methods: {cooking_methods}")
        app.logger.info(f"User kitchen tools: {kitchen_tools}")

        # Add filter constraints to the prompt
        constraints = []
        if filters.get('timeConstraint'):
            constraints.append(f"- Must take less than {filters['timeConstraint']} minutes to prepare")
        if filters.get('preferredMethod'):
            method_name = COOKING_METHODS.get(filters['preferredMethod'], {}).get('name')
            if method_name:
                constraints.append(f"- Must use {method_name} as the primary cooking method")
        if filters.get('dietary'):
            constraints.extend([f"- Must be {pref}" for pref in filters['dietary']])
        if filters.get('mustUseIngredients'):
            must_use = [item.name for item in inventory_items if str(item.id) in filters['mustUseIngredients']]
            if must_use:
                constraints.append(f"- Must use these ingredients: {', '.join(must_use)}")
        
        constraints_text = "\n".join(constraints) if constraints else "No specific constraints"

        # Always request 10 recipes initially
        recipes_to_request = 10
        app.logger.info(f"Requesting {recipes_to_request} recipes")

        system_prompt = """You are a helpful cooking assistant. When suggesting recipes:
1. Format each recipe clearly with sections for name, ingredients, and instructions
2. Start each recipe with 'Recipe: ' followed by the name
3. List ingredients with quantities and units (e.g., '2 cups of flour' not '2 cup flour')
4. Provide clear, step-by-step instructions
5. Include preparation time
6. Consider the user's available cooking methods and tools
7. Separate required ingredients (from the list) and additional ingredients needed
8. Never list 'none' or empty ingredients
9. Use proper units (e.g., 'piece' instead of 'pcs', '1 piece' vs '2 pieces')
10. Each recipe must use at least 2 ingredients from the available inventory
11. Suggest creative but practical recipes based on the available ingredients
12. Make sure each recipe is unique and different from the others"""

        user_prompt = f"""Based on these available ingredients:
{ingredients_text}

Using these cooking methods and tools:
Cooking Methods: {', '.join(cooking_methods) if cooking_methods else 'Any'}
Kitchen Tools: {', '.join(kitchen_tools) if kitchen_tools else 'Basic kitchen tools'}

With these constraints:
{constraints_text}

Please suggest {recipes_to_request} unique and different recipes that can be made using some or all of these ingredients. 
Each recipe must use at least 2 ingredients from my inventory and should be distinctly different from the others.
For each recipe, include:
1. Recipe name (start with 'Recipe: ')
2. Required ingredients from my inventory (with quantities)
3. Additional ingredients needed (with quantities)
4. Preparation time
5. Clear cooking instructions that utilize the available cooking methods and tools

Available ingredients summary: {', '.join(ingredients_summary)}"""

        # Call OpenAI API
        try:
            completion = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,
                max_tokens=4000
            )
            app.logger.info("Successfully received OpenAI API response")
            
            response_text = completion.choices[0].message.content
            app.logger.info(f"OpenAI response text:\n{response_text}")
            
            recipes = parse_recipe_suggestions(response_text)
            app.logger.info(f"Parsed {len(recipes)} recipes")
            
            return jsonify({'recipes': recipes})

        except Exception as api_error:
            app.logger.error(f"OpenAI API error: {str(api_error)}")
            raise

    except Exception as e:
        app.logger.error(f"Error generating recipes: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_single_recipe', methods=['POST'])
@login_required
def get_single_recipe():
    """Generate a single new recipe to replace a removed one"""
    try:
        # Use the same logic as get_recipes but request only one recipe
        request.args = dict(request.args)
        request.args['current_count'] = '9'  # Pretend we have 9 recipes to get 1 more
        response = get_recipes()
        if response.status_code == 200:
            data = response.get_json()
            if data.get('recipes'):
                return jsonify({'recipe': data['recipes'][0]})
        return jsonify({'error': 'Failed to generate new recipe'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def clean_unit(quantity, unit):
    # Convert float to int if it's a whole number
    if isinstance(quantity, (int, float)):
        if quantity.is_integer():
            quantity = int(quantity)
    
    # Clean up unit names
    unit_mapping = {
        'pcs': 'piece',
        'pc': 'piece',
        'pieces': 'piece',
        'g': 'grams',
        'ml': 'milliliters',
        'l': 'liters',
        'oz': 'ounces',
        'lb': 'pounds',
        'tsp': 'teaspoon',
        'tbsp': 'tablespoon',
        'cup': 'cups',
    }
    
    # Handle pluralization
    if unit.lower() in unit_mapping:
        base_unit = unit_mapping[unit.lower()]
        if quantity == 1:
            return f"{quantity} {base_unit}"
        else:
            # Handle special cases
            if base_unit == 'piece':
                return f"{quantity} pieces"
            return f"{quantity} {base_unit}s"
    
    return f"{quantity} {unit}"

def parse_recipe_suggestions(response_text):
    recipes = []
    current_recipe = None
    current_section = None
    
    # Split response into lines and process each line
    lines = response_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Start a new recipe when we see "Recipe:"
        if line.lower().startswith('recipe:'):
            if current_recipe:
                if current_recipe.get('name') and current_recipe.get('instructions'):
                    recipes.append(current_recipe)
            
            current_recipe = {
                'name': line.replace('Recipe:', '').strip(),
                'required_ingredients': [],
                'additional_ingredients': [],
                'preparation_time': 'Not specified',
                'instructions': []
            }
            current_section = None
            
        # Process sections within a recipe
        elif current_recipe:
            lower_line = line.lower()
            
            # Check for section headers
            if any(header in lower_line for header in ['required ingredients:', 'ingredients from inventory:', 'from your inventory:']):
                current_section = 'required_ingredients'
                
            elif any(header in lower_line for header in ['additional ingredients:', 'extra ingredients:', 'other ingredients:']):
                current_section = 'additional_ingredients'
                
            elif any(header in lower_line for header in ['preparation time:', 'prep time:', 'cooking time:', 'total time:']):
                current_recipe['preparation_time'] = line.split(':', 1)[1].strip()
                current_section = None
                
            elif any(header in lower_line for header in ['instructions:', 'steps:', 'directions:', 'method:']):
                current_section = 'instructions'
                
            # Process content based on current section
            elif current_section:
                # Handle list items (both numbered and bulleted)
                if line.startswith(('-', '•', '*')) or re.match(r'^\d+\.?\s', line):
                    content = re.sub(r'^[-•*\d.]\s*', '', line).strip()
                    
                    if current_section == 'instructions':
                        if content:
                            current_recipe['instructions'].append(content)
                    else:  # ingredients sections
                        if content.lower() not in ['none', 'n/a', '-']:
                            current_recipe[current_section].append(content)
                
                # Handle non-list items in instructions
                elif current_section == 'instructions' and line:
                    current_recipe['instructions'].append(line)
        
        i += 1
    
    # Add the last recipe if it exists
    if current_recipe and current_recipe.get('name') and current_recipe.get('instructions'):
        recipes.append(current_recipe)
    
    # Clean up recipes
    for recipe in recipes:
        # Remove duplicates while preserving order
        for section in ['required_ingredients', 'additional_ingredients']:
            seen = set()
            recipe[section] = [x for x in recipe[section] if not (x.lower() in seen or seen.add(x.lower()))]
        
        # Clean up and number instructions
        recipe['instructions'] = [
            f"{i+1}. {instr.strip()}" 
            for i, instr in enumerate(recipe['instructions']) 
            if instr.strip()
        ]
        
        # Ensure preparation time is set
        if not recipe['preparation_time'] or recipe['preparation_time'] == 'Not specified':
            recipe['preparation_time'] = '30-40 minutes'  # Default value
    
    app.logger.info(f"Parsed {len(recipes)} recipes: {[r['name'] for r in recipes]}")
    return recipes

@app.route('/delete_all_inventory', methods=['POST'])
@login_required
def delete_all_inventory():
    try:
        # Delete all inventory items for the current user
        InventoryItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash('All inventory items have been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting inventory items.', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/add_test_items')
@login_required
def add_test_items():
    try:
        # Sample items
        test_items = [
            {'name': 'Chicken Breast', 'quantity': 2, 'unit': 'pcs'},
            {'name': 'Rice', 'quantity': 500, 'unit': 'g'},
            {'name': 'Tomatoes', 'quantity': 3, 'unit': 'pcs'},
            {'name': 'Onion', 'quantity': 2, 'unit': 'pcs'},
            {'name': 'Garlic', 'quantity': 5, 'unit': 'cloves'}
        ]

        # Add items to inventory
        for item in test_items:
            new_item = InventoryItem(
                name=item['name'],
                quantity=item['quantity'],
                unit=item['unit'],
                user_id=current_user.id
            )
            db.session.add(new_item)
        
        db.session.commit()
        return jsonify({'message': 'Test items added successfully'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding test items: {str(e)}")
        return jsonify({'error': 'Failed to add test items'}), 500

@app.route('/rate_recipe', methods=['POST'])
@login_required
def rate_recipe():
    data = request.json
    recipe_name = data.get('recipe_name')
    rating = data.get('rating')  # true for like, false for dislike
    
    if not recipe_name:
        return jsonify({'error': 'Recipe name is required'}), 400
        
    # Check if rating already exists
    existing_rating = RecipeRating.query.filter_by(
        user_id=current_user.id,
        recipe_name=recipe_name
    ).first()
    
    if existing_rating:
        existing_rating.rating = rating
    else:
        new_rating = RecipeRating(
            recipe_name=recipe_name,
            user_id=current_user.id,
            rating=rating
        )
        db.session.add(new_rating)
    
    db.session.commit()
    return jsonify({'message': 'Rating saved successfully'})

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'Message is required'}), 400

        # Create the chat prompt
        inventory_items = InventoryItem.query.filter_by(user_id=current_user.id).all()
        ingredients_list = "\n".join([f"- {item.quantity} {item.unit} of {item.name}" for item in inventory_items])
        
        system_prompt = """You are a helpful cooking assistant. When suggesting recipes:
1. Format each recipe clearly with sections for name, ingredients, and instructions
2. Start each recipe with 'Recipe: ' followed by the name
3. List ingredients with bullet points (-)
4. Provide clear, step-by-step instructions
5. Include preparation time
6. Consider the user's available ingredients when suggesting recipes
7. Be conversational and friendly"""

        user_prompt = f"""Available ingredients:
{ingredients_list}

User request: {user_message}

Please provide recipe suggestions based on the request and available ingredients. If specific ingredients are missing, suggest alternatives or additional items needed."""

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        # Get the response text
        assistant_response = response.choices[0].message.content

        # Save the chat message
        chat_message = ChatMessage(
            user_id=current_user.id,
            message=user_message,
            response=assistant_response
        )
        db.session.add(chat_message)
        db.session.commit()

        # Parse any recipes in the response
        recipes = parse_recipe_suggestions(assistant_response)
        
        return jsonify({
            'message': assistant_response,
            'recipes': recipes
        })

    except Exception as e:
        app.logger.error(f"Chat error: {str(e)}")
        app.logger.exception("Full traceback:")
        return jsonify({
            'error': 'Failed to process chat message',
            'details': str(e)
        }), 500

@app.route('/refresh_recipe/<recipe_name>', methods=['POST'])
@login_required
def refresh_recipe():
    try:
        recipe_name = request.json.get('recipe_name')
        if not recipe_name:
            return jsonify({'error': 'Recipe name is required'}), 400

        # Get user's inventory items
        inventory_items = InventoryItem.query.filter_by(user_id=current_user.id).all()
        ingredients_list = "\n".join([f"- {item.quantity} {item.unit} of {item.name}" for item in inventory_items])

        # Create a specific prompt for the recipe
        prompt = f"""Based on these available ingredients:
{ingredients_list}

Please provide a new variation of the recipe '{recipe_name}'. Include:
1. Recipe name (keep it similar but with a twist)
2. Required ingredients from the list (with bullet points)
3. Additional ingredients needed (with bullet points)
4. Preparation time
5. Clear cooking instructions"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful cooking assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1000
        )

        recipes = parse_recipe_suggestions(response.choices[0].message.content)
        if recipes:
            return jsonify({'recipe': recipes[0]})
        else:
            return jsonify({'error': 'Could not generate a new recipe variation'}), 500

    except Exception as e:
        app.logger.error(f"Error refreshing recipe: {str(e)}")
        return jsonify({'error': 'Failed to refresh recipe'}), 500

@app.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    if request.method == 'POST':
        cooking_methods = request.form.getlist('cooking_methods')
        kitchen_tools = request.form.getlist('kitchen_tools')
        
        current_user.cooking_methods = cooking_methods
        current_user.kitchen_tools = kitchen_tools
        db.session.commit()
        
        flash('Preferences updated successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('preferences.html', 
                         cooking_methods=COOKING_METHODS,
                         kitchen_tools=KITCHEN_TOOLS,
                         user_cooking_methods=current_user.cooking_methods or [],
                         user_kitchen_tools=current_user.kitchen_tools or [])

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