from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import csv
import io
from collections import defaultdict
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/fintrack/data/expense_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade='all, delete-orphan')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.now().date)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route("/health")
def health():
    return {"status": "ok"}, 200
    
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return render_template('register.html')
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get recent expenses
    recent_expenses = Expense.query.filter_by(user_id=current_user.id)\
                                 .order_by(Expense.date.desc())\
                                 .limit(5).all()
    
    # Get current month total
    today = datetime.now().date()
    start_of_month = datetime(today.year, today.month, 1).date()
    monthly_total = db.session.query(db.func.sum(Expense.amount))\
                             .filter(Expense.user_id == current_user.id,
                                   Expense.date >= start_of_month)\
                             .scalar() or 0
    
    # Get category breakdown for current month
    category_data = db.session.query(Expense.category, db.func.sum(Expense.amount))\
                             .filter(Expense.user_id == current_user.id,
                                   Expense.date >= start_of_month)\
                             .group_by(Expense.category).all()
    
    return render_template('dashboard.html', 
                         recent_expenses=recent_expenses,
                         monthly_total=monthly_total,
                         category_data=category_data)

@app.route('/expenses')
@login_required
def expenses():
    page = request.args.get('page', 1, type=int)
    expenses = Expense.query.filter_by(user_id=current_user.id)\
                           .order_by(Expense.date.desc())\
                           .paginate(page=page, per_page=10, error_out=False)
    return render_template('expenses.html', expenses=expenses)

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        description = request.form['description']
        category = request.form['category']
        date_str = request.form['date']
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        expense = Expense(
            amount=amount,
            description=description,
            category=category,
            date=date,
            user_id=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        
        flash('Expense added successfully')
        return redirect(url_for('expenses'))
    
    return render_template('add_expense.html')

@app.route('/edit_expense/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    expense = Expense.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        expense.amount = float(request.form['amount'])
        expense.description = request.form['description']
        expense.category = request.form['category']
        expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        
        db.session.commit()
        flash('Expense updated successfully')
        return redirect(url_for('expenses'))
    
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete_expense/<int:id>')
@login_required
def delete_expense(id):
    expense = Expense.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully')
    return redirect(url_for('expenses'))

@app.route('/analytics')
@login_required
def analytics():
    # Monthly totals for the last 12 months
    monthly_data = []
    for i in range(12):
        date = datetime.now() - timedelta(days=30*i)
        start_of_month = datetime(date.year, date.month, 1).date()
        if date.month == 12:
            end_of_month = datetime(date.year + 1, 1, 1).date()
        else:
            end_of_month = datetime(date.year, date.month + 1, 1).date()
        
        total = db.session.query(db.func.sum(Expense.amount))\
                         .filter(Expense.user_id == current_user.id,
                               Expense.date >= start_of_month,
                               Expense.date < end_of_month)\
                         .scalar() or 0
        
        monthly_data.append({
            'month': calendar.month_name[date.month],
            'year': date.year,
            'total': total
        })
    
    monthly_data.reverse()
    
    # Category breakdown for all time
    category_totals = db.session.query(Expense.category, db.func.sum(Expense.amount))\
                               .filter(Expense.user_id == current_user.id)\
                               .group_by(Expense.category).all()
    
    return render_template('analytics.html', 
                         monthly_data=monthly_data,
                         category_totals=category_totals)

@app.route('/export_csv')
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id)\
                           .order_by(Expense.date.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Description', 'Category', 'Amount'])
    
    for expense in expenses:
        writer.writerow([
            expense.date.strftime('%Y-%m-%d'),
            expense.description,
            expense.category,
            expense.amount
        ])
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=expenses.csv'
    response.headers['Content-type'] = 'text/csv'
    
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
