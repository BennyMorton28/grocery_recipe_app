# Grocery Recipe App

A smart recipe suggestion application that helps you make the most of your groceries and reduce food waste.

## Features

- Track your grocery inventory with quantities and expiry dates
- Get personalized recipe suggestions based on your available ingredients
- Upload receipts using your camera or from your photo library
- Set cooking preferences and dietary restrictions
- Like/dislike recipes to improve suggestions
- Mobile-friendly interface

## Setup

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/grocery_recipe_app.git
cd grocery_recipe_app
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file in the project root and add:
```
FLASK_APP=app.py
FLASK_ENV=development
OPENAI_API_KEY=your_api_key_here
```

4. Initialize the database:
```bash
flask db upgrade
```

5. Run the application:
```bash
python app.py
```

The app will be available at `http://localhost:8080`

## Usage

1. Register an account and set your cooking preferences
2. Add items to your inventory manually or by uploading receipts
3. View recipe suggestions based on your available ingredients
4. Rate recipes to improve future suggestions
5. Track your inventory and get notified of expiring items

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b new-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin new-feature`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Project Structure

```
grocery_recipe_app/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── static/            # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── img/
└── templates/         # HTML templates
    ├── base.html
    ├── index.html
    ├── login.html
    ├── register.html
    └── dashboard.html
```

## Acknowledgments

- Bootstrap for the UI components
- Flask for the web framework
- SQLAlchemy for the database ORM 