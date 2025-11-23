from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from collections import defaultdict
import pandas as pd
import io
import base64
import os
import matplotlib.pyplot as plt
import json  # Import the json module

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SECRET_KEY'] = os.urandom(24)  # Generate a strong secret key
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    expenses = db.relationship('Expense', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Expense {self.id}>'

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_category_bar_chart(expenses):
    category_totals = defaultdict(float)
    for expense in expenses:
        category_totals[expense.category] += expense.amount
    if not category_totals:
        return None
    categories = list(category_totals.keys())
    totals = list(category_totals.values())
    plt.figure(figsize=(10, 6))
    plt.bar(categories, totals, color='skyblue')
    plt.xlabel('Category')
    plt.ylabel('Total Amount')
    plt.title('Expenses by Category')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    return f'data:image/png;base64,{plot_url}'

def generate_time_series_plot_matplotlib(expenses):
    if not expenses:
        return None
    df = pd.DataFrame([(exp.date, exp.amount) for exp in expenses], columns=['date', 'amount'])
    df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
    monthly_totals = df.groupby('month')['amount'].sum().sort_index()
    if monthly_totals.empty:
        return None
    plt.figure(figsize=(10, 6))
    plt.plot(monthly_totals.index.astype(str), monthly_totals.values, marker='o', linestyle='-')
    plt.xlabel('Month')
    plt.ylabel('Total Amount')
    plt.title('Monthly Expenses Over Time')
    plt.grid(True)
    plt.tight_layout()
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    return f'data:image/png;base64,{plot_url}'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists. Please choose another one.')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        category = request.form['category']
        new_expense = Expense(description=description, amount=amount, category=category, user_id=current_user.id)
        db.session.add(new_expense)
        db.session.commit()
        return redirect(url_for('view_expenses'))
    return render_template('add_expense.html')

@app.route('/edit_expense/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    expense_to_edit = Expense.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        expense_to_edit.description = request.form['description']
        expense_to_edit.amount = float(request.form['amount'])
        expense_to_edit.category = request.form['category']
        db.session.commit()
        flash('Expense updated successfully!', 'success')
        return redirect(url_for('view_expenses'))
    return render_template('edit_expense.html', expense=expense_to_edit)

@app.route('/view_expenses', methods=['GET', 'POST'])
@login_required
def view_expenses():
    category_filter = request.form.get('category_filter')
    expenses_query = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc())

    if category_filter and category_filter != 'all':
        expenses_query = expenses_query.filter_by(category=category_filter)

    expenses = expenses_query.all()
    all_categories = [expense.category for expense in Expense.query.filter_by(user_id=current_user.id).distinct().all()]
    all_categories = sorted(list(set(all_categories)))
    all_categories.insert(0, 'all') # Add 'all' option for no filter

    return render_template('view_expenses.html', expenses=expenses, all_categories=all_categories, current_filter=category_filter)

@app.route('/delete_expense/<int:id>')
@login_required
def delete_expense(id):
    expense_to_delete = Expense.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(expense_to_delete)
    db.session.commit()
    flash('Expense deleted successfully!', 'success')
    return redirect(url_for('view_expenses'))

@app.route('/summary')
@login_required
def show_summary():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()

    # Pie Chart
    category_totals_pie = defaultdict(float)
    for expense in expenses:
        category_totals_pie[expense.category] += expense.amount
    pie_plot_url = None
    print("category_totals_pie:", category_totals_pie) # Debugging
    if category_totals_pie:
        labels = list(category_totals_pie.keys())
        sizes = list(category_totals_pie.values())
        print("Pie Chart Labels:", labels) # Debugging
        print("Pie Chart Sizes:", sizes) # Debugging
        plt.figure(figsize=(8, 8))
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.title('Expenses by Category')
        plt.axis('equal')
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode()
        pie_plot_url = f'data:image/png;base64,{plot_url}'
        print("Generated pie_plot_url (first 50 chars):", pie_plot_url[:50]) # Debugging
        plt.close()
    else:
        print("No category data for pie chart.") # Debugging

    # Bar Chart
    bar_plot_url = generate_category_bar_chart(expenses)

    # Time Series Plot
    time_series_plot_url = generate_time_series_plot_matplotlib(expenses)

    return render_template(
        'summary.html',
        pie_plot_url=pie_plot_url,
        bar_plot_url=bar_plot_url,
        time_series_plot_url=time_series_plot_url,
        has_expenses=bool(expenses),
        category_totals_pie_json=json.dumps(category_totals_pie),
        monthly_totals_json=json.dumps(dict(sorted(defaultdict(float).items()))) # Initialize empty for now
    )

if __name__ == '__main__':
    app.run(debug=True)