from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
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
import base64

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

# Load environment variables from absolute path
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

# Debug prints
print("Environment variables:")
print("MONGO_URI:", os.getenv('MONGO_URI'))
print("FLASK_APP:", os.getenv('FLASK_APP'))
print("SECRET_KEY:", os.getenv('SECRET_KEY'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config["MONGO_URI"] = os.getenv("MONGO_URI")

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic', 'heif'}

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize OpenAI client
client = OpenAI()  # This will automatically use OPENAI_API_KEY from environment

# Initialize MongoDB
mongo = PyMongo(app)

# Database Models
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data.get('_id'))
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password_hash')
        self.cooking_methods = user_data.get('cooking_methods', [])
        self.kitchen_tools = user_data.get('kitchen_tools', [])
        self.preferences = user_data.get('preferences', {})

    def get_id(self):
        return self.id

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

def clean_quantity(quantity):
    """Clean and validate quantity value."""
    try:
        # Convert to float if it's a string
        if isinstance(quantity, str):
            quantity = float(quantity)
        
        # Ensure it's a positive number
        if quantity <= 0:
            return 1.0  # Default to 1 if invalid
            
        return float(quantity)
    except (ValueError, TypeError):
        return 1.0  # Default to 1 if conversion fails

def clean_price(price):
    """Clean and validate price value."""
    try:
        # Convert to float if it's a string
        if isinstance(price, str):
            price = float(price)
        
        # Ensure it's a non-negative number
        if price < 0:
            return 0.0
            
        return float(price)
    except (ValueError, TypeError):
        return 0.0  # Default to 0 if conversion fails

def process_receipt(receipt_path):
    """Process receipt image using OpenAI Vision API"""
    try:
        app.logger.info(f"Starting receipt processing for file: {receipt_path}")
        
        # Step 1: Check if file exists
        if not os.path.exists(receipt_path):
            app.logger.error(f"File not found: {receipt_path}")
            raise FileNotFoundError(f"File not found: {receipt_path}")
            
        # Step 2: Encode image to base64
        app.logger.info("Encoding image to base64...")
        with open(receipt_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        app.logger.info(f"Image encoded successfully. Base64 length: {len(base64_image)}")
        
        # Step 3: Prepare the API request
        app.logger.info("Preparing OpenAI API request...")
        request_data = {
            "model": "gpt-4o",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please analyze this receipt and extract all grocery items. For each item, provide: name, quantity, unit, and price. Format the response as a JSON array with these fields. Example: [{\"name\": \"Milk\", \"quantity\": 1, \"unit\": \"gallon\", \"price\": 3.99}]. Return ONLY the JSON array, no other text or formatting."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }],
            "max_tokens": 1000
        }
        app.logger.info("API request prepared")
        
        # Step 4: Make the API call
        app.logger.info("Making OpenAI API call...")
        response = client.chat.completions.create(**request_data)
        app.logger.info("API call completed successfully")
        
        # Step 5: Log the raw response
        app.logger.info(f"Raw OpenAI API Response: {response.choices[0].message.content}")
        
        # Step 6: Clean up the response text
        app.logger.info("Cleaning response text...")
        clean_response = response.choices[0].message.content.strip()
        
        # Remove markdown formatting if present
        if clean_response.startswith("```"):
            clean_response = clean_response.split("\n", 1)[1]  # Remove first line
        if clean_response.endswith("```"):
            clean_response = clean_response.rsplit("\n", 1)[0]  # Remove last line
        if clean_response.startswith("json"):
            clean_response = clean_response.split("\n", 1)[1]  # Remove json tag
            
        app.logger.info(f"Cleaned response: {clean_response}")
        
        # Step 7: Parse the response
        app.logger.info("Parsing response...")
        try:
            items = json.loads(clean_response)
            if not isinstance(items, list):
                app.logger.error("Response is not a list of items")
                raise ValueError("Response is not a list of items")
            
            app.logger.info(f"Found {len(items)} items in response")
            
            # Step 8: Clean and validate each item
            cleaned_items = []
            for item in items:
                try:
                    app.logger.info(f"Processing item: {item}")
                    # Clean and validate the item
                    cleaned_item = {
                        'name': item.get('name', '').strip(),
                        'quantity': float(item.get('quantity', 1)),
                        'unit': item.get('unit', '').strip().lower(),
                        'price': float(item.get('price', 0))
                    }
                    cleaned_items.append(cleaned_item)
                    app.logger.info(f"Cleaned item: {cleaned_item}")
                except Exception as e:
                    app.logger.error(f"Error cleaning item {item}: {str(e)}")
                    continue
            
            app.logger.info(f"Successfully processed {len(cleaned_items)} items from receipt")
            return cleaned_items
            
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to parse receipt response: {clean_response}")
            app.logger.error(f"JSON decode error: {str(e)}")
            raise ValueError("Failed to parse receipt data")
            
    except Exception as e:
        app.logger.error(f"Error processing receipt: {str(e)}")
        app.logger.exception("Full traceback:")
        raise
    finally:
        # Clean up the uploaded file
        try:
            os.remove(receipt_path)
            app.logger.info(f"Cleaned up temporary file: {receipt_path}")
        except Exception as e:
            app.logger.warning(f"Failed to remove temporary file: {str(e)}")

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
        cooking_methods = request.form.getlist('cooking_methods')
        kitchen_tools = request.form.getlist('kitchen_tools')
        
        # Check if username or email already exists
        if mongo.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash('Username or email already exists', 'error')
            return redirect(url_for('register'))
        
        # Create new user with pbkdf2:sha256 method
        user_data = {
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password, method='pbkdf2:sha256'),
            "cooking_methods": cooking_methods,
            "kitchen_tools": kitchen_tools,
            "preferences": {},
            "date_created": datetime.utcnow()
        }
        
        result = mongo.db.users.insert_one(user_data)
        # Get the complete user data including the _id
        user_data['_id'] = result.inserted_id
        
        # Create User object and log them in
        user = User(user_data)
        login_user(user)
        
        flash('Registration successful! Welcome to Grocery Recipe App!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('register.html', 
                         cooking_methods=COOKING_METHODS,
                         kitchen_tools=KITCHEN_TOOLS)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = mongo.db.users.find_one({"username": username})
        
        if user_data and check_password_hash(user_data.get('password_hash', ''), password):
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
    inventory = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
    receipts = list(mongo.db.receipts.find({"user_id": ObjectId(current_user.id)}).sort("upload_date", -1))
    return render_template('dashboard.html', inventory=inventory, receipts=receipts)

@app.route('/api/upload_receipt', methods=['POST'])
@login_required
def upload_receipt():
    """Handle receipt upload and processing."""
    app.logger.info("Starting receipt upload process")
    app.logger.info(f"Request files: {request.files}")
    app.logger.info(f"Request form: {request.form}")
    
    if 'receipt' not in request.files:
        app.logger.error("No receipt file in request")
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['receipt']
    app.logger.info(f"Received file: {file.filename}")
    
    if file.filename == '':
        app.logger.error("Empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        app.logger.error(f"Invalid file type: {file.filename}")
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        # Create a unique filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        app.logger.info(f"Saving file to {filepath}")
        file.save(filepath)
        app.logger.info("File saved successfully")
        
        app.logger.info("Processing receipt with OpenAI Vision API")
        try:
            # Process the receipt
            items = process_receipt(filepath)
            
            if not items:
                app.logger.warning("No items found in receipt")
                return jsonify({'error': 'No items found in receipt'}), 400
            
            app.logger.info(f"Successfully processed {len(items)} items")
            app.logger.info(f"Processed items: {items}")
            
            # Return the items for user confirmation
            return jsonify({
                'success': True,
                'items': items,
                'message': f'Found {len(items)} items. Please review and confirm.'
            }), 200
            
        except Exception as process_error:
            app.logger.error(f"Error processing receipt: {str(process_error)}")
            app.logger.exception("Full traceback:")
            return jsonify({
                'error': 'Failed to process receipt',
                'details': str(process_error)
            }), 500
            
    except Exception as save_error:
        app.logger.error(f"Error saving file: {str(save_error)}")
        app.logger.exception("Full traceback:")
        return jsonify({
            'error': 'Failed to save file',
            'details': str(save_error)
        }), 500
    
    finally:
        # Clean up the uploaded file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                app.logger.info(f"Cleaned up file: {filepath}")
        except Exception as cleanup_error:
            app.logger.error(f"Error during cleanup: {str(cleanup_error)}")
            app.logger.exception("Full traceback:")

@app.route('/api/confirm_receipt_items', methods=['POST'])
@login_required
def confirm_receipt_items():
    """Handle user confirmation of receipt items"""
    app.logger.info("Processing receipt items confirmation")
    
    try:
        data = request.json
        items = data.get('items', [])
        
        if not items:
            app.logger.error("No items provided for confirmation")
            return jsonify({'error': 'No items provided'}), 400
        
        app.logger.info(f"Processing {len(items)} confirmed items")
        
        # Add confirmed items to inventory
        for item in items:
            try:
                inventory_item = {
                    'user_id': ObjectId(current_user.id),
                    'name': item['name'],
                    'quantity': float(item['quantity']),
                    'unit': item['unit'],
                    'date_added': datetime.utcnow()
                }
                
                result = mongo.db.inventory.insert_one(inventory_item)
                app.logger.info(f"Added item to inventory: {item['name']}")
                
            except Exception as item_error:
                app.logger.error(f"Error adding item to inventory: {str(item_error)}")
                continue
        
        app.logger.info("Successfully processed all confirmed items")
        return jsonify({
            'success': True,
            'message': f'Successfully added {len(items)} items to inventory'
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error confirming receipt items: {str(e)}")
        app.logger.exception("Full traceback:")
        return jsonify({
            'error': 'Failed to confirm receipt items',
            'details': str(e)
        }), 500

@app.route('/delete_item/<item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    result = mongo.db.inventory.delete_one({
        '_id': ObjectId(item_id),
        'user_id': ObjectId(current_user.id)
    })
    if result.deleted_count == 0:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify({'message': 'Item deleted successfully'})

@app.route('/api/add_item', methods=['POST'])
@login_required
def add_item():
    """Handle adding a single item to inventory"""
    app.logger.info("Processing add item request")
    
    try:
        data = request.json
        app.logger.info(f"Received item data: {data}")
        
        if not data:
            app.logger.error("No data provided")
            return jsonify({'error': 'No data provided'}), 400
        
        # Handle both direct item data and items array format
        if 'items' in data and isinstance(data['items'], list):
            # If data is in the format {"items": [{"name": "...", ...}]}
            if len(data['items']) > 0:
                item_data = data['items'][0]  # Take the first item
            else:
                app.logger.error("Empty items array provided")
                return jsonify({'error': 'Empty items array provided'}), 400
        else:
            # If data is directly the item {"name": "...", ...}
            item_data = data
        
        # Validate required fields
        required_fields = ['name', 'quantity', 'unit', 'price']
        for field in required_fields:
            if field not in item_data:
                app.logger.error(f"Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create inventory item
        inventory_item = {
            'user_id': ObjectId(current_user.id),
            'name': item_data['name'],
            'quantity': float(item_data['quantity']),
            'unit': item_data['unit'],
            'price': float(item_data['price']),
            'date_added': datetime.utcnow()
        }
        
        app.logger.info(f"Adding item to inventory: {inventory_item}")
        result = mongo.db.inventory.insert_one(inventory_item)
        app.logger.info(f"Successfully added item with ID: {result.inserted_id}")
        
        return jsonify({
            'success': True,
            'message': 'Item added successfully',
            'item_id': str(result.inserted_id)
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error adding item: {str(e)}")
        app.logger.exception("Full traceback:")
        return jsonify({
            'error': 'Failed to add item',
            'details': str(e)
        }), 500

@app.route('/get_recipes')
@login_required
def get_recipes():
    try:
        inventory_items = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
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
            if item['quantity'] and item['unit']:
                formatted_amount = clean_unit(item['quantity'], item['unit'])
                ingredients_list.append(f"- {formatted_amount} of {item['name']}")
                ingredients_summary.append(f"{formatted_amount} of {item['name']}")
            else:
                ingredients_list.append(f"- {item['name']}")
                ingredients_summary.append(item['name'])

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
            must_use = [item['name'] for item in inventory_items if str(item['_id']) in filters['mustUseIngredients']]
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
                model="gpt-4o",
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

def clean_unit(unit, quantity=None):
    """Clean and validate unit value."""
    try:
        # If quantity is provided, use the two-parameter version
        if quantity is not None:
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
        
        # Single parameter version - just clean the unit
        unit = unit.lower().strip()
        if not unit:
            return 'piece'  # Default unit
            
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
        
        return unit_mapping.get(unit, unit)
        
    except Exception as e:
        app.logger.error(f"Error cleaning unit: {str(e)}")
        return 'piece'  # Default unit on error

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
        result = mongo.db.inventory.delete_many({"user_id": ObjectId(current_user.id)})
        if result.deleted_count >= 0:
            return jsonify({"message": f"Deleted {result.deleted_count} items"})
        else:
            return jsonify({"error": "Failed to delete inventory"}), 500
    except Exception as e:
        app.logger.error(f"Error deleting all inventory: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

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
            item['user_id'] = ObjectId(current_user.id)
            item['date_added'] = datetime.utcnow()
            mongo.db.inventory.insert_one(item)
        
        return jsonify({'message': 'Test items added successfully'})
    except Exception as e:
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
    existing_rating = mongo.db.recipe_ratings.find_one({
        'user_id': ObjectId(current_user.id),
        'recipe_name': recipe_name
    })
    
    if existing_rating:
        mongo.db.recipe_ratings.update_one(
            {'_id': existing_rating['_id']},
            {'$set': {'rating': rating}}
        )
    else:
        new_rating = {
            'recipe_name': recipe_name,
            'user_id': ObjectId(current_user.id),
            'rating': rating,
            'created_at': datetime.utcnow()
        }
        mongo.db.recipe_ratings.insert_one(new_rating)
    
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
        inventory_items = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
        ingredients_list = "\n".join([f"- {item['quantity']} {item['unit']} of {item['name']}" for item in inventory_items])
        
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
            model="gpt-4o",
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
        chat_message = {
            'user_id': ObjectId(current_user.id),
            'message': user_message,
            'response': assistant_response,
            'created_at': datetime.utcnow()
        }
        mongo.db.chat_messages.insert_one(chat_message)

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
        inventory_items = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
        ingredients_list = "\n".join([f"- {item['quantity']} {item['unit']} of {item['name']}" for item in inventory_items])

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
            model="gpt-4o",
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
        
        flash('Preferences updated successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('preferences.html', 
                         cooking_methods=COOKING_METHODS,
                         kitchen_tools=KITCHEN_TOOLS,
                         user_cooking_methods=current_user.cooking_methods or [],
                         user_kitchen_tools=current_user.kitchen_tools or [])

@app.route('/api/inventory', methods=['GET', 'POST'])
@login_required
def inventory():
    if request.method == 'GET':
        try:
            # Get user's inventory
            items = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
            # Convert ObjectId to string for JSON serialization
            for item in items:
                item['_id'] = str(item['_id'])
                item['user_id'] = str(item['user_id'])
                # Convert any datetime objects to string if they exist
                if 'added_date' in item:
                    item['added_date'] = item['added_date'].isoformat()
            return jsonify({"items": items})
        except Exception as e:
            app.logger.error(f"Error getting inventory: {str(e)}")
            return jsonify({"error": "Failed to get inventory"}), 500
    
    elif request.method == 'POST':
        try:
            data = request.json
            if not all(k in data for k in ['name', 'quantity', 'unit']):
                return jsonify({"error": "Missing required fields"}), 400
            
            # Clean and validate the data
            name = data['name'].strip()
            quantity = float(data['quantity'])
            unit = data['unit'].strip().lower()
            
            if not name or quantity <= 0:
                return jsonify({"error": "Invalid item data"}), 400
            
            # Add the item to inventory
            item = {
                "user_id": ObjectId(current_user.id),
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "added_date": datetime.utcnow()
            }
            
            result = mongo.db.inventory.insert_one(item)
            
            if result.inserted_id:
                return jsonify({
                    "message": "Item added successfully",
                    "item_id": str(result.inserted_id)
                }), 201
            else:
                return jsonify({"error": "Failed to add item"}), 500
                
        except ValueError as e:
            return jsonify({"error": "Invalid quantity value"}), 400
        except Exception as e:
            app.logger.error(f"Error adding item: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500

@app.route('/delete_all_users', methods=['GET'])
def delete_all_users():
    try:
        result = mongo.db.users.delete_many({})
        flash(f'Successfully deleted {result.deleted_count} users from the database.', 'success')
    except Exception as e:
        flash(f'Error deleting users: {str(e)}', 'error')
    return redirect(url_for('register'))

@app.route('/api/analyze-receipt', methods=['POST'])
@login_required
def analyze_receipt():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload an image file.'}), 400
        
        # Save the file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Process the receipt using our vision-based function
            items = process_receipt(filepath)
            
            # Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)
            
            return jsonify({
                'success': True,
                'items': items
            })
            
        except Exception as e:
            # Clean up the uploaded file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
            app.logger.error(f"Error processing receipt: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
            
    except Exception as e:
        app.logger.error(f"Error analyzing receipt: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/suggested_recipes')
@login_required
def get_suggested_recipes():
    try:
        # Get user's inventory items
        inventory = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
        
        # Format inventory items for the prompt
        inventory_text = "\n".join([f"- {item['quantity']} {item['unit']} of {item['name']}" for item in inventory])
        
        # Create the prompt for recipe generation
        response = client.responses.create(
            model="gpt-4o",
            input=[
                {
                    "role": "developer",
                    "content": """You are a creative chef. Generate 3 diverse recipe suggestions based on the available ingredients.
                    Each recipe should:
                    1. Use at least 2-3 ingredients from the inventory
                    2. Be realistic and practical to make
                    3. Include a brief description
                    4. List required ingredients (marking which ones are available in inventory)
                    5. Include approximate cooking time
                    
                    Format each recipe in JSON as:
                    {
                        "name": "Recipe Name",
                        "description": "Brief description",
                        "cooking_time": "XX minutes",
                        "ingredients": {
                            "from_inventory": ["item1", "item2"],
                            "additional_needed": ["item3", "item4"]
                        }
                    }
                    
                    Return an array of 3 recipe objects."""
                },
                {
                    "role": "user",
                    "content": f"Available ingredients:\n{inventory_text}"
                }
            ]
        )
        
        # Parse the response
        try:
            # Clean up markdown formatting if present
            clean_response = response.output_text.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("\n", 1)[1]  # Remove first line
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]  # Remove last line
            if clean_response.startswith("json"):
                clean_response = clean_response.split("\n", 1)[1]  # Remove json tag
                
            recipes = json.loads(clean_response)
            return jsonify({"recipes": recipes})
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to parse recipe response: {response.output_text}")
            app.logger.error(f"JSON decode error: {str(e)}")
            return jsonify({"error": "Failed to generate recipes"}), 500
            
    except Exception as e:
        app.logger.error(f"Error generating recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat_recipes', methods=['POST'])
@login_required
def chat_recipes():
    try:
        query = request.json.get('query')
        if not query:
            return jsonify({"error": "No query provided"}), 400

        # Get user's inventory
        inventory = list(mongo.db.inventory.find({"user_id": ObjectId(current_user.id)}))
        inventory_text = "\n".join([f"- {item['quantity']} {item['unit']} of {item['name']}" for item in inventory])

        # Generate recipes based on query and inventory
        response = client.responses.create(
            model="gpt-4o",
            input=[
                {
                    "role": "developer",
                    "content": """You are a creative chef. Based on the user's query and available ingredients, generate 3 relevant recipe suggestions.
                    Each recipe should:
                    1. Match the user's request (time, dietary restrictions, etc.)
                    2. Use available ingredients when possible
                    3. Include detailed steps
                    4. Be practical and realistic
                    
                    Format the response in JSON as:
                    {
                        "recipes": [
                            {
                                "name": "Recipe Name",
                                "description": "Brief description",
                                "cooking_time": "XX minutes",
                                "ingredients": {
                                    "from_inventory": ["item1", "item2"],
                                    "additional_needed": ["item3", "item4"]
                                },
                                "steps": ["step1", "step2", "step3"]
                            }
                        ]
                    }"""
                },
                {
                    "role": "user",
                    "content": f"Query: {query}\n\nAvailable ingredients:\n{inventory_text}"
                }
            ]
        )

        try:
            # Clean up markdown formatting if present
            clean_response = response.output_text.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("\n", 1)[1]  # Remove first line
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]  # Remove last line
            if clean_response.startswith("json"):
                clean_response = clean_response.split("\n", 1)[1]  # Remove json tag
                
            recipes = json.loads(clean_response)
            return jsonify(recipes)
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to parse chat recipe response: {response.output_text}")
            app.logger.error(f"JSON decode error: {str(e)}")
            return jsonify({"error": "Failed to generate recipes"}), 500

    except Exception as e:
        app.logger.error(f"Error in chat recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/inventory/<item_id>', methods=['DELETE'])
@login_required
def delete_inventory_item(item_id):
    try:
        # Verify the item belongs to the current user
        item = mongo.db.inventory.find_one({
            "_id": ObjectId(item_id),
            "user_id": ObjectId(current_user.id)
        })
        
        if not item:
            return jsonify({"error": "Item not found"}), 404
            
        # Delete the item
        result = mongo.db.inventory.delete_one({
            "_id": ObjectId(item_id),
            "user_id": ObjectId(current_user.id)
        })
        
        if result.deleted_count > 0:
            return jsonify({"message": "Item deleted successfully"})
        else:
            return jsonify({"error": "Failed to delete item"}), 500
            
    except Exception as e:
        app.logger.error(f"Error deleting item: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

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
    
    # Enable more detailed logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    app.run(
        debug=True,
        host='0.0.0.0',  # Listen on all available network interfaces
        port=8080,
        threaded=True    # Enable threading for better performance
    ) 