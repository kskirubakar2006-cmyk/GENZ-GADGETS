import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime
import json
from sqlalchemy import text

from models import db, Admin, Product, Supplier, Customer, Purchase, Sale

app = Flask(__name__)
app.config['SECRET_KEY'] = 'genz_gadget_hub_inventory_secret_1337'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///genz_gadget_hub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

# Initialize database
print('[INFO] initializing database...')
db.init_app(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

@app.after_request
def add_no_store_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@login_manager.user_loader
def load_user(user_id):
    try:
        if user_id.startswith('admin_'):
            admin_id = int(user_id.split('_')[1])
            return Admin.query.get(admin_id)
    except Exception:
        return None
    return None

# Access control decorator

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.get_id().startswith('admin_'):
            flash('Please log in as an administrator to access this area.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_global_data():
    categories = ['Mobile phones', 'Laptops', 'Smart watches', 'Gaming consoles', 'Earbuds', 'Accessories']
    low_stock_alerts = 0
    is_admin = False
    if current_user.is_authenticated and current_user.get_id().startswith('admin_'):
        is_admin = True
        low_stock_alerts = Product.query.filter(Product.stock_quantity > 0, Product.stock_quantity < 10).count()
    return dict(categories=categories, low_stock_alerts=low_stock_alerts, is_admin=is_admin)


def count_table_rows(table_name):
    try:
        inspector = db.inspect(db.engine)
        if not inspector.has_table(table_name):
            return 0
        result = db.session.execute(text(f'SELECT COUNT(*) AS count FROM {table_name}'))
        return int(result.scalar() or 0)
    except Exception:
        return 0


def count_todays_sales():
    try:
        inspector = db.inspect(db.engine)
        if not inspector.has_table('sales'):
            return 0
        columns = [column['name'] for column in inspector.get_columns('sales')]
        if 'sale_date' in columns:
            result = db.session.execute(text("SELECT COUNT(*) AS count FROM sales WHERE date(sale_date) = date('now')"))
            return int(result.scalar() or 0)
        return count_table_rows('sales')
    except Exception:
        return 0


def supplier_exists(company_name, supplier_id=None):
    name = (company_name or '').strip()
    if not name:
        return False
    query = Supplier.query.filter(Supplier.company_name.ilike(name))
    if supplier_id:
        query = query.filter(Supplier.id != supplier_id)
    return query.first() is not None


def customer_exists(customer_name, email=None, phone=None):
    name = (customer_name or '').strip()
    if not name:
        return False
    query = Customer.query.filter(Customer.customer_name.ilike(name))
    if email:
        query = query.filter(Customer.email.ilike(email))
    if phone:
        query = query.filter(Customer.phone == phone)
    return query.first() is not None

@app.route('/')
def root_redirect():
    if current_user.is_authenticated and current_user.get_id().startswith('admin_'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and current_user.get_id().startswith('admin_'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            login_user(admin)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully.', 'info')
    response = redirect(url_for('login'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    products = Product.query.order_by(Product.id.desc()).all()
    total_products = len(products)
    
    # Low stock
    low_stock_products_all = Product.query.filter(Product.stock_quantity < 10).order_by(Product.stock_quantity.asc()).all()
    low_stock_items = len(low_stock_products_all)
    top_low_stock = low_stock_products_all[:5]
    
    # Recent Sales
    recent_sales = Sale.query.order_by(Sale.id.desc()).limit(5).all()
    
    # Analytics Data
    
    category_counts = {}
    for p in products:
        category_counts[p.category] = category_counts.get(p.category, 0) + 1
    chart_category_labels = list(category_counts.keys())
    chart_category_data = list(category_counts.values())
    
    sales = Sale.query.order_by(Sale.sale_date.asc()).all()
    sales_by_month = {}
    for s in sales:
        month = s.sale_date.strftime('%b %Y')
        sales_by_month[month] = sales_by_month.get(month, 0) + (s.selling_price * s.quantity)
    
    chart_sales_labels = list(sales_by_month.keys())
    chart_sales_data = list(sales_by_month.values())
    
    today = datetime.now()
    
    return render_template(
        'dashboard.html',
        top_low_stock=top_low_stock,
        total_products=total_products,
        total_suppliers=count_table_rows('suppliers'),
        total_customers=count_table_rows('customers'),
        todays_sales=count_todays_sales(),
        low_stock_items=low_stock_items,
        recent_sales=recent_sales,
        current_date=today.strftime('%d %b %Y'),
        current_time=today.strftime('%I:%M:%S %p'),
        welcome_name=current_user.username.title(),
        chart_category_labels=json.dumps(chart_category_labels),
        chart_category_data=json.dumps(chart_category_data),
        chart_sales_labels=json.dumps(chart_sales_labels),
        chart_sales_data=json.dumps(chart_sales_data)
    )

@app.route('/inventory')
@login_required
@admin_required
def inventory():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    product_query = Product.query
    if query:
        product_query = product_query.filter(
            (Product.name.ilike(f'%{query}%')) | 
            (Product.brand.ilike(f'%{query}%')) | 
            (Product.category.ilike(f'%{query}%'))
        )
    if category:
        product_query = product_query.filter(Product.category == category)
    products = product_query.order_by(Product.id.desc()).all()
    return render_template('inventory.html', products=products, query=query, active_category=category)

@app.route('/inventory/adjust-stock/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def adjust_stock(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json() or {}
    delta = data.get('delta', 0)
    new_stock = product.stock_quantity + delta
    if new_stock < 0:
        return jsonify({'status': 'error', 'message': 'Stock count cannot be negative.'}), 400
    product.stock_quantity = new_stock
    db.session.commit()
    badge_class = 'badge-success'
    badge_text = f'In Stock: {product.stock_quantity}'
    if product.stock_quantity == 0:
        badge_class = 'badge-danger'
        badge_text = 'Out of Stock'
    elif product.stock_quantity < 5:
        badge_class = 'badge-danger'
        badge_text = f'Critical Stock: {product.stock_quantity}'
    elif product.stock_quantity < 10:
        badge_class = 'badge-warning'
        badge_text = f'Low Stock: {product.stock_quantity}'
    return jsonify({'status': 'success', 'new_stock': product.stock_quantity, 'badge_class': badge_class, 'badge_text': badge_text})

@app.route('/inventory/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand = request.form.get('brand', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        try:
            price = float(request.form.get('price'))
            stock_quantity = int(request.form.get('stock_quantity'))
        except (TypeError, ValueError):
            flash('Price and stock quantity must be valid numbers.', 'danger')
            return redirect(url_for('admin_add_product'))
            
        if not name:
            flash('Product name cannot be empty.', 'danger')
            return redirect(url_for('admin_add_product'))
        if price <= 0:
            flash('Price must be greater than 0.', 'danger')
            return redirect(url_for('admin_add_product'))
        if stock_quantity < 0:
            flash('Stock cannot be negative.', 'danger')
            return redirect(url_for('admin_add_product'))
        specs = {
            'Display': request.form.get('spec_display', 'N/A').strip(),
            'Processor': request.form.get('spec_processor', 'N/A').strip(),
            'RAM': request.form.get('spec_ram', 'N/A').strip(),
            'Storage': request.form.get('spec_storage', 'N/A').strip(),
            'Battery': request.form.get('spec_battery', 'N/A').strip(),
        }
        image_file = request.files.get('image_file')
        image_url = None
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(upload_path)
            image_url = f'/static/uploads/{filename}'
        else:
            image_url = '/static/uploads/default_placeholder.svg'
        new_prod = Product(name=name, brand=brand, category=category, price=price, description=description, image_url=image_url, stock_quantity=stock_quantity)
        new_prod.specs = specs
        db.session.add(new_prod)
        db.session.commit()
        flash(f"Product '{name}' created in inventory successfully.", 'success')
        return redirect(url_for('inventory'))
    return render_template('product_form.html', product=None)

@app.route('/inventory/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        if not product.name:
            flash('Product name cannot be empty.', 'danger')
            return redirect(url_for('admin_edit_product', product_id=product_id))
            
        product.brand = request.form.get('brand', '').strip()
        product.category = request.form.get('category', '').strip()
        try:
            price = float(request.form.get('price'))
            stock_quantity = int(request.form.get('stock_quantity'))
        except (TypeError, ValueError):
            flash('Price and stock quantity must be valid numbers.', 'danger')
            return redirect(url_for('admin_edit_product', product_id=product_id))
            
        if price <= 0:
            flash('Price must be greater than 0.', 'danger')
            return redirect(url_for('admin_edit_product', product_id=product_id))
        if stock_quantity < 0:
            flash('Stock cannot be negative.', 'danger')
            return redirect(url_for('admin_edit_product', product_id=product_id))
            
        product.price = price
        product.stock_quantity = stock_quantity
        product.description = request.form.get('description').strip()
        product.specs = {
            'Display': request.form.get('spec_display', 'N/A').strip(),
            'Processor': request.form.get('spec_processor', 'N/A').strip(),
            'RAM': request.form.get('spec_ram', 'N/A').strip(),
            'Storage': request.form.get('spec_storage', 'N/A').strip(),
            'Battery': request.form.get('spec_battery', 'N/A').strip(),
        }
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(upload_path)
            product.image_url = f'/static/uploads/{filename}'
        db.session.commit()
        flash('Product updated successfully.', 'success')
        return redirect(url_for('inventory'))
    return render_template('product_form.html', product=product)

@app.route('/inventory/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f"Product '{name}' removed from inventory.", 'warning')
    return redirect(url_for('inventory'))

@app.route('/suppliers', methods=['GET'])
@login_required
@admin_required
def suppliers():
    query = request.args.get('q', '').strip()
    supplier_query = Supplier.query
    if query:
        supplier_query = supplier_query.filter(
            (Supplier.company_name.ilike(f'%{query}%')) |
            (Supplier.contact_person.ilike(f'%{query}%')) |
            (Supplier.phone.ilike(f'%{query}%'))
        )
    suppliers_list = supplier_query.order_by(Supplier.id.desc()).all()
    return render_template('suppliers.html', suppliers=suppliers_list, query=query, supplier=None)

@app.route('/suppliers/add', methods=['POST'])
@login_required
@admin_required
def add_supplier():
    company_name = request.form.get('company_name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()

    if not company_name:
        flash('Company name is required.', 'danger')
        return redirect(url_for('suppliers'))
    if supplier_exists(company_name):
        flash('Duplicate company name already exists.', 'danger')
        return redirect(url_for('suppliers'))

    supplier = Supplier(
        company_name=company_name,
        contact_person=contact_person or None,
        phone=phone or None,
        email=email or None,
        address=address or None,
    )
    db.session.add(supplier)
    db.session.commit()
    flash('Supplier added successfully.', 'success')
    return redirect(url_for('suppliers'))

@app.route('/suppliers/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if request.method == 'POST':
        new_company_name = request.form.get('company_name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        
        if not new_company_name:
            flash('Company name is required.', 'danger')
            return redirect(url_for('edit_supplier', supplier_id=supplier_id))
            
        if new_company_name.lower() != supplier.company_name.lower() and supplier_exists(new_company_name, supplier_id=supplier_id):
            flash('Duplicate company name already exists.', 'danger')
            return redirect(url_for('edit_supplier', supplier_id=supplier_id))
            
        supplier.company_name = new_company_name
        supplier.contact_person = request.form.get('contact_person', '').strip() or None
        supplier.phone = phone
        supplier.email = email
        supplier.address = request.form.get('address', '').strip() or None
        db.session.commit()
        flash('Supplier updated successfully.', 'success')
        return redirect(url_for('suppliers'))

    query = request.args.get('q', '').strip()
    supplier_query = Supplier.query
    if query:
        supplier_query = supplier_query.filter(
            (Supplier.company_name.ilike(f'%{query}%')) |
            (Supplier.contact_person.ilike(f'%{query}%')) |
            (Supplier.phone.ilike(f'%{query}%'))
        )
    suppliers_list = supplier_query.order_by(Supplier.id.desc()).all()
    return render_template('suppliers.html', suppliers=suppliers_list, query=query, supplier=supplier)

@app.route('/suppliers/delete/<int:supplier_id>', methods=['POST'])
@login_required
@admin_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)
    db.session.commit()
    flash('Supplier deleted successfully.', 'warning')
    return redirect(url_for('suppliers'))

@app.route('/customers', methods=['GET'])
@login_required
@admin_required
def customers():
    query = request.args.get('q', '').strip()
    customer_query = Customer.query
    if query:
        customer_query = customer_query.filter(
            (Customer.customer_name.ilike(f'%{query}%')) |
            (Customer.phone.ilike(f'%{query}%')) |
            (Customer.email.ilike(f'%{query}%'))
        )
    customers_list = customer_query.order_by(Customer.id.desc()).all()
    return render_template('customers.html', customers=customers_list, query=query, customer=None)

@app.route('/customers/add', methods=['POST'])
@login_required
@admin_required
def add_customer():
    customer_name = request.form.get('customer_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()

    if not customer_name:
        flash('Customer name is required.', 'danger')
        return redirect(url_for('customers'))
        
    if email and Customer.query.filter(Customer.email.ilike(email)).first():
        flash('Duplicate email address already exists.', 'danger')
        return redirect(url_for('customers'))
    if phone and Customer.query.filter(Customer.phone == phone).first():
        flash('Duplicate phone number already exists.', 'danger')
        return redirect(url_for('customers'))

    customer = Customer(
        customer_name=customer_name,
        phone=phone or None,
        email=email or None,
        address=address or None,
    )
    db.session.add(customer)
    db.session.commit()
    flash('Customer added successfully.', 'success')
    return redirect(url_for('customers'))

@app.route('/customers/edit/<int:customer_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        new_customer_name = request.form.get('customer_name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        
        if not new_customer_name:
            flash('Customer name is required.', 'danger')
            return redirect(url_for('edit_customer', customer_id=customer_id))
            
        if email and Customer.query.filter(Customer.email.ilike(email), Customer.id != customer_id).first():
            flash('Duplicate email address already exists.', 'danger')
            return redirect(url_for('edit_customer', customer_id=customer_id))
        if phone and Customer.query.filter(Customer.phone == phone, Customer.id != customer_id).first():
            flash('Duplicate phone number already exists.', 'danger')
            return redirect(url_for('edit_customer', customer_id=customer_id))
            
        customer.customer_name = new_customer_name
        customer.phone = phone
        customer.email = email
        customer.address = request.form.get('address', '').strip() or None
        db.session.commit()
        flash(f"Customer '{customer.customer_name}' updated successfully.", 'success')
        return redirect(url_for('customers'))

    query = request.args.get('q', '').strip()
    customer_query = Customer.query
    if query:
        customer_query = customer_query.filter(
            (Customer.customer_name.ilike(f'%{query}%')) |
            (Customer.phone.ilike(f'%{query}%')) |
            (Customer.email.ilike(f'%{query}%'))
        )
    customers_list = customer_query.order_by(Customer.id.desc()).all()
    return render_template('customers.html', customers=customers_list, query=query, customer=customer)

@app.route('/customers/delete/<int:customer_id>', methods=['POST'])
@login_required
@admin_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    name = customer.customer_name
    db.session.delete(customer)
    db.session.commit()
    flash(f"Customer '{name}' removed successfully.", 'warning')
    return redirect(url_for('customers'))

@app.route('/purchases', methods=['GET'])
@login_required
@admin_required
def purchases():
    from sqlalchemy import cast, String
    query = request.args.get('q', '').strip()
    purchase_query = Purchase.query
    if query:
        purchase_query = purchase_query.join(Supplier).join(Product).filter(
            (Supplier.company_name.ilike(f'%{query}%')) |
            (Product.name.ilike(f'%{query}%')) |
            (cast(Purchase.purchase_date, String).ilike(f'%{query}%'))
        )
    purchases_list = purchase_query.order_by(Purchase.id.desc()).all()
    suppliers = Supplier.query.order_by(Supplier.company_name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('purchases.html', purchases=purchases_list, suppliers=suppliers, products=products, query=query, purchase=None)

@app.route('/purchases/add', methods=['POST'])
@login_required
@admin_required
def add_purchase():
    supplier_id = request.form.get('supplier_id', type=int)
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int)
    purchase_price = request.form.get('purchase_price', type=float)
    purchase_date = request.form.get('purchase_date', '').strip() or datetime.utcnow().date().isoformat()

    if not supplier_id or not product_id:
        flash('Supplier and Product are required.', 'danger')
        return redirect(url_for('purchases'))
    if quantity is None or quantity <= 0:
        flash('Quantity must be greater than 0.', 'danger')
        return redirect(url_for('purchases'))
    if purchase_price is None or purchase_price <= 0:
        flash('Purchase price must be greater than 0.', 'danger')
        return redirect(url_for('purchases'))

    supplier = Supplier.query.get(supplier_id)
    product = Product.query.get(product_id)
    if not supplier or not product:
        flash('Invalid supplier or product selected.', 'danger')
        return redirect(url_for('purchases'))

    purchase = Purchase(supplier_id=supplier_id, product_id=product_id, quantity=quantity, purchase_price=purchase_price, purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d').date())
    db.session.add(purchase)
    product.stock_quantity += quantity
    db.session.commit()
    flash('Purchase recorded successfully.', 'success')
    return redirect(url_for('purchases'))

@app.route('/purchases/edit/<int:purchase_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id', type=int)
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=int)
        purchase_price = request.form.get('purchase_price', type=float)
        purchase_date = request.form.get('purchase_date', '').strip() or datetime.utcnow().date().isoformat()

        if not supplier_id or not product_id:
            flash('Supplier and Product are required.', 'danger')
            return redirect(url_for('edit_purchase', purchase_id=purchase_id))
        if quantity is None or quantity <= 0:
            flash('Quantity must be greater than 0.', 'danger')
            return redirect(url_for('edit_purchase', purchase_id=purchase_id))
        if purchase_price is None or purchase_price <= 0:
            flash('Purchase price must be greater than 0.', 'danger')
            return redirect(url_for('edit_purchase', purchase_id=purchase_id))

        new_product = Product.query.get(product_id)
        if not new_product:
            flash('Invalid product selected.', 'danger')
            return redirect(url_for('edit_purchase', purchase_id=purchase_id))
            
        if purchase.product_id == product_id:
            if purchase.product.stock_quantity - purchase.quantity + quantity < 0:
                flash('Cannot update purchase. It would result in negative stock.', 'danger')
                return redirect(url_for('edit_purchase', purchase_id=purchase_id))
        else:
            if purchase.product.stock_quantity - purchase.quantity < 0:
                flash('Cannot update purchase. It would result in negative stock for the old product.', 'danger')
                return redirect(url_for('edit_purchase', purchase_id=purchase_id))

        purchase.product.stock_quantity -= purchase.quantity
        purchase.supplier_id = supplier_id
        purchase.product_id = product_id
        purchase.quantity = quantity
        purchase.purchase_price = purchase_price
        purchase.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
        
        new_product.stock_quantity += quantity
        db.session.commit()
        flash('Purchase updated successfully.', 'success')
        return redirect(url_for('purchases'))

    from sqlalchemy import cast, String
    query = request.args.get('q', '').strip()
    purchase_query = Purchase.query
    if query:
        purchase_query = purchase_query.join(Supplier).join(Product).filter(
            (Supplier.company_name.ilike(f'%{query}%')) |
            (Product.name.ilike(f'%{query}%')) |
            (cast(Purchase.purchase_date, String).ilike(f'%{query}%'))
        )
    purchases_list = purchase_query.order_by(Purchase.id.desc()).all()
    suppliers = Supplier.query.order_by(Supplier.company_name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('purchases.html', purchases=purchases_list, suppliers=suppliers, products=products, query=query, purchase=purchase)

@app.route('/purchases/delete/<int:purchase_id>', methods=['POST'])
@login_required
@admin_required
def delete_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    if purchase.product.stock_quantity - purchase.quantity < 0:
        flash('Cannot delete this purchase. It would result in negative stock.', 'danger')
        return redirect(url_for('purchases'))
        
    purchase.product.stock_quantity -= purchase.quantity
    db.session.delete(purchase)
    db.session.commit()
    flash('Purchase deleted and stock adjusted.', 'warning')
    return redirect(url_for('purchases'))

@app.route('/sales', methods=['GET'])
@login_required
@admin_required
def sales():
    from sqlalchemy import cast, String
    query = request.args.get('q', '').strip()
    sale_query = Sale.query
    if query:
        sale_query = sale_query.join(Customer).join(Product).filter(
            (Customer.customer_name.ilike(f'%{query}%')) |
            (Product.name.ilike(f'%{query}%')) |
            (cast(Sale.sale_date, String).ilike(f'%{query}%'))
        )
    sales_list = sale_query.order_by(Sale.id.desc()).all()
    customers = Customer.query.order_by(Customer.customer_name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('sales.html', sales=sales_list, customers=customers, products=products, query=query, sale=None)

@app.route('/sales/add', methods=['POST'])
@login_required
@admin_required
def add_sale():
    customer_id = request.form.get('customer_id', type=int)
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int)
    selling_price = request.form.get('selling_price', type=float)
    sale_date = request.form.get('sale_date', '').strip() or datetime.utcnow().date().isoformat()

    if not customer_id or not product_id:
        flash('Customer and Product are required.', 'danger')
        return redirect(url_for('sales'))
    if quantity is None or quantity <= 0:
        flash('Quantity must be greater than 0.', 'danger')
        return redirect(url_for('sales'))
    if selling_price is None or selling_price <= 0:
        flash('Selling price must be greater than 0.', 'danger')
        return redirect(url_for('sales'))

    customer = Customer.query.get(customer_id)
    product = Product.query.get(product_id)
    if not customer or not product:
        flash('Invalid customer or product selected.', 'danger')
        return redirect(url_for('sales'))
    if product.stock_quantity < quantity:
        flash('Insufficient stock available.', 'danger')
        return redirect(url_for('sales'))

    sale = Sale(customer_id=customer_id, product_id=product_id, quantity=quantity, selling_price=selling_price, sale_date=datetime.strptime(sale_date, '%Y-%m-%d').date())
    db.session.add(sale)
    product.stock_quantity -= quantity
    db.session.commit()
    flash('Sale completed successfully.', 'success')
    return redirect(url_for('sales'))

@app.route('/sales/edit/<int:sale_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if request.method == 'POST':
        customer_id = request.form.get('customer_id', type=int)
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=int)
        selling_price = request.form.get('selling_price', type=float)
        sale_date = request.form.get('sale_date', '').strip() or datetime.utcnow().date().isoformat()

        if not customer_id or not product_id:
            flash('Customer and Product are required.', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))
        if quantity is None or quantity <= 0:
            flash('Quantity must be greater than 0.', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))
        if selling_price is None or selling_price <= 0:
            flash('Selling price must be greater than 0.', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))

        new_product = Product.query.get(product_id)
        if not new_product:
            flash('Invalid product selected.', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))
            
        # Check if the new product has enough stock
        # If it's the same product, we can add back the current sale quantity for the check
        available_stock = new_product.stock_quantity
        if new_product.id == sale.product_id:
            available_stock += sale.quantity
            
        if available_stock < quantity:
            flash('Insufficient stock available.', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))

        sale.product.stock_quantity += sale.quantity
        sale.customer_id = customer_id
        sale.product_id = product_id
        sale.quantity = quantity
        sale.selling_price = selling_price
        sale.sale_date = datetime.strptime(sale_date, '%Y-%m-%d').date()
        new_product.stock_quantity -= quantity
        db.session.commit()
        flash('Sale updated successfully.', 'success')
        return redirect(url_for('sales'))

    from sqlalchemy import cast, String
    query = request.args.get('q', '').strip()
    sale_query = Sale.query
    if query:
        sale_query = sale_query.join(Customer).join(Product).filter(
            (Customer.customer_name.ilike(f'%{query}%')) |
            (Product.name.ilike(f'%{query}%')) |
            (cast(Sale.sale_date, String).ilike(f'%{query}%'))
        )
    sales_list = sale_query.order_by(Sale.id.desc()).all()
    customers = Customer.query.order_by(Customer.customer_name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('sales.html', sales=sales_list, customers=customers, products=products, query=query, sale=sale)

@app.route('/sales/delete/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def delete_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    sale.product.stock_quantity += sale.quantity
    db.session.delete(sale)
    db.session.commit()
    flash('Sale deleted and stock adjusted.', 'warning')
    return redirect(url_for('sales'))


@app.route('/reports')
@login_required
@admin_required
def reports():
    report_type = request.args.get('type', 'inventory')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    export = request.args.get('export', '')

    inventory_data = []
    purchase_data = []
    sales_data = []
    
    total_inventory_value = 0
    total_purchase_amount = 0
    total_sales_amount = 0

    if report_type == 'inventory':
        inventory_data = Product.query.order_by(Product.name).all()
        for p in inventory_data:
            total_inventory_value += (p.stock_quantity * p.price)
            
    elif report_type == 'purchase':
        query = Purchase.query.join(Supplier).join(Product)
        if start_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Purchase.purchase_date >= sd)
            except ValueError:
                pass
        if end_date:
            try:
                ed = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Purchase.purchase_date <= ed)
            except ValueError:
                pass
        purchase_data = query.order_by(Purchase.purchase_date.desc()).all()
        for p in purchase_data:
            total_purchase_amount += (p.quantity * p.purchase_price)
            
    elif report_type == 'sales':
        query = Sale.query.join(Customer).join(Product)
        if start_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Sale.sale_date >= sd)
            except ValueError:
                pass
        if end_date:
            try:
                ed = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Sale.sale_date <= ed)
            except ValueError:
                pass
        sales_data = query.order_by(Sale.sale_date.desc()).all()
        for s in sales_data:
            total_sales_amount += (s.quantity * s.selling_price)
            
    if export == 'csv':
        import csv
        import io
        from flask import Response
        
        si = io.StringIO()
        cw = csv.writer(si)
        
        if report_type == 'inventory':
            cw.writerow(['Product', 'Stock', 'Price', 'Total Value'])
            for item in inventory_data:
                cw.writerow([item.name, item.stock_quantity, f"{item.price:.2f}", f"{item.stock_quantity * item.price:.2f}"])
            cw.writerow(['', '', 'Total Inventory Value', f"{total_inventory_value:.2f}"])
        elif report_type == 'purchase':
            cw.writerow(['Date', 'Supplier', 'Product', 'Quantity', 'Purchase Price'])
            for item in purchase_data:
                cw.writerow([item.purchase_date, item.supplier.company_name, item.product.name, item.quantity, f"{item.purchase_price:.2f}"])
            cw.writerow(['', '', '', 'Total Purchases', f"{total_purchase_amount:.2f}"])
        elif report_type == 'sales':
            cw.writerow(['Date', 'Customer', 'Product', 'Quantity', 'Selling Price'])
            for item in sales_data:
                cw.writerow([item.sale_date, item.customer.customer_name, item.product.name, item.quantity, f"{item.selling_price:.2f}"])
            cw.writerow(['', '', '', 'Total Sales', f"{total_sales_amount:.2f}"])
            
        output = si.getvalue()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={report_type}_report.csv"}
        )
            
    return render_template(
        'reports.html',
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        inventory_data=inventory_data,
        purchase_data=purchase_data,
        sales_data=sales_data,
        total_inventory_value=total_inventory_value,
        total_purchase_amount=total_purchase_amount,
        total_sales_amount=total_sales_amount
    )

def ensure_supplier_columns():
    inspector = db.inspect(db.engine)
    if not inspector.has_table('suppliers'):
        return

    columns = {column['name'] for column in inspector.get_columns('suppliers')}
    if 'name' in columns:
        if 'company_name' not in columns:
            db.session.execute(text("ALTER TABLE suppliers ADD COLUMN company_name VARCHAR(150) NOT NULL DEFAULT ''"))
            db.session.execute(text("UPDATE suppliers SET company_name = name WHERE company_name = ''"))
        
        db.session.execute(text("ALTER TABLE suppliers RENAME TO suppliers_old"))
        
        db.session.execute(text('''
            CREATE TABLE suppliers (
                id INTEGER NOT NULL PRIMARY KEY,
                company_name VARCHAR(150) NOT NULL,
                contact_person VARCHAR(100),
                phone VARCHAR(50),
                email VARCHAR(120),
                address TEXT,
                created_at DATETIME
            )
        '''))
        
        db.session.execute(text('''
            INSERT INTO suppliers (id, company_name, contact_person, phone, email, address, created_at)
            SELECT id, 
                   CASE WHEN company_name != '' THEN company_name ELSE name END, 
                   contact_person, phone, email, address, created_at
            FROM suppliers_old
        '''))
        
        db.session.execute(text("DROP TABLE suppliers_old"))
        db.session.commit()

    # Check if purchases table is referencing suppliers_old
    try:
        purchase_create_sql = db.session.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='purchases'")).scalar()
        if purchase_create_sql and "suppliers_old" in purchase_create_sql:
            db.session.execute(text("ALTER TABLE purchases RENAME TO purchases_old"))
            
            db.session.execute(text('''
                CREATE TABLE purchases (
                    id INTEGER NOT NULL, 
                    supplier_id INTEGER NOT NULL, 
                    product_id INTEGER NOT NULL, 
                    quantity INTEGER NOT NULL, 
                    purchase_price FLOAT NOT NULL, 
                    purchase_date DATE NOT NULL, 
                    created_at DATETIME, 
                    PRIMARY KEY (id), 
                    FOREIGN KEY(supplier_id) REFERENCES suppliers (id), 
                    FOREIGN KEY(product_id) REFERENCES products (id)
                )
            '''))
            
            db.session.execute(text('''
                INSERT INTO purchases (id, supplier_id, product_id, quantity, purchase_price, purchase_date, created_at)
                SELECT id, supplier_id, product_id, quantity, purchase_price, purchase_date, created_at
                FROM purchases_old
            '''))
            
            db.session.execute(text("DROP TABLE purchases_old"))
            db.session.commit()
    except Exception:
        pass


def seed_products():
    if Product.query.first() is not None:
        return

    sample_products = [
        Product(name='Apple AirPods Pro', brand='Apple', category='Earbuds', price=24999, description='Noise-cancelling earbuds with wireless charging case', stock_quantity=12, image_url='/static/uploads/default_placeholder.svg'),
        Product(name='Sony WH-1000XM5', brand='Sony', category='Headphones', price=29999, description='Premium noise-cancelling headphones', stock_quantity=8, image_url='/static/uploads/default_placeholder.svg'),
        Product(name='JBL Flip 6', brand='JBL', category='Speakers', price=11999, description='Portable waterproof Bluetooth speaker', stock_quantity=20, image_url='/static/uploads/default_placeholder.svg'),
        Product(name='Logitech G502', brand='Logitech', category='Mouse', price=4999, description='High-performance gaming mouse', stock_quantity=15, image_url='/static/uploads/default_placeholder.svg'),
        Product(name='Dell Mechanical Keyboard', brand='Dell', category='Keyboard', price=3499, description='Mechanical keyboard with tactile switches', stock_quantity=25, image_url='/static/uploads/default_placeholder.svg'),
    ]
    db.session.add_all(sample_products)
    db.session.commit()


def seed_suppliers():
    if Supplier.query.first() is not None:
        return

    sample_suppliers = [
        Supplier(company_name='ABC Electronics', contact_person='Rajesh Kumar', phone='9876543210', email='rajesh@abcelectronics.com', address='Coimbatore'),
        Supplier(company_name='Tech World Pvt Ltd', contact_person='Priya Sharma', phone='9876501234', email='priya@techworld.com', address='Chennai'),
        Supplier(company_name='Digital Traders', contact_person='Arun Kumar', phone='9123456789', email='arun@digitaltraders.com', address='Bangalore'),
        Supplier(company_name='Future Gadgets', contact_person='Deepak', phone='9000011111', email='deepak@futuregadgets.com', address='Hyderabad'),
    ]
    db.session.add_all(sample_suppliers)
    db.session.commit()


def seed_customers():
    if Customer.query.first() is not None:
        return

    sample_customers = [
        Customer(customer_name='Rahul', phone='9876543210', email='rahul@gmail.com', address='Coimbatore'),
        Customer(customer_name='Priya', phone='9876501234', email='priya@gmail.com', address='Chennai'),
        Customer(customer_name='Karthik', phone='9123456789', email='karthik@gmail.com', address='Salem'),
        Customer(customer_name='Sneha', phone='9345678901', email='sneha@gmail.com', address='Erode'),
        Customer(customer_name='Ajay', phone='9789012345', email='ajay@gmail.com', address='Madurai'),
    ]
    db.session.add_all(sample_customers)
    db.session.commit()


def seed_purchases():
    if Purchase.query.first() is not None:
        return

    purchases_data = [
        {'supplier': 'ABC Electronics', 'product': 'Samsung Galaxy S24', 'category': 'Mobile phones', 'brand': 'Samsung', 'qty': 10, 'price': 58000.0},
        {'supplier': 'Tech World Pvt Ltd', 'product': 'Dell Inspiron 15', 'category': 'Laptops', 'brand': 'Dell', 'qty': 5, 'price': 48500.0},
        {'supplier': 'Digital Traders', 'product': 'Redmi Note 14 Pro', 'category': 'Mobile phones', 'brand': 'Xiaomi', 'qty': 20, 'price': 18000.0},
        {'supplier': 'Future Gadgets', 'product': 'Apple AirPods Pro', 'category': 'Earbuds', 'brand': 'Apple', 'qty': 15, 'price': 16500.0},
        {'supplier': 'ABC Electronics', 'product': 'HP Pavilion Laptop', 'category': 'Laptops', 'brand': 'HP', 'qty': 8, 'price': 52000.0},
        {'supplier': 'Tech World Pvt Ltd', 'product': 'Boat Rockerz 550', 'category': 'Accessories', 'brand': 'boAt', 'qty': 25, 'price': 1450.0},
        {'supplier': 'Digital Traders', 'product': 'Logitech Wireless Mouse', 'category': 'Accessories', 'brand': 'Logitech', 'qty': 40, 'price': 550.0},
        {'supplier': 'Future Gadgets', 'product': 'Sony WH-CH520 Headphones', 'category': 'Accessories', 'brand': 'Sony', 'qty': 12, 'price': 3200.0},
    ]

    for item in purchases_data:
        supplier = Supplier.query.filter_by(company_name=item['supplier']).first()
        if not supplier:
            supplier = Supplier(company_name=item['supplier'])
            db.session.add(supplier)
            db.session.flush()

        product = Product.query.filter_by(name=item['product']).first()
        if not product:
            product = Product(
                name=item['product'], 
                brand=item['brand'], 
                category=item['category'], 
                price=item['price'] * 1.2,
                stock_quantity=0,
                image_url='/static/uploads/default_placeholder.svg'
            )
            db.session.add(product)
            db.session.flush()

        purchase = Purchase(
            supplier_id=supplier.id,
            product_id=product.id,
            quantity=item['qty'],
            purchase_price=item['price'],
            purchase_date=datetime.utcnow().date()
        )
        db.session.add(purchase)
        product.stock_quantity += item['qty']
        
    db.session.commit()


def seed_sales():
    if Sale.query.first() is not None:
        return

    sales_data = [
        {'customer': 'Arun Kumar', 'product': 'Samsung Galaxy S24', 'qty': 2, 'price': 64999.0},
        {'customer': 'Priya Sharma', 'product': 'Dell Inspiron 15', 'qty': 1, 'price': 55000.0},
        {'customer': 'Rahul Verma', 'product': 'Redmi Note 14 Pro', 'qty': 3, 'price': 22500.0},
        {'customer': 'Sneha R', 'product': 'Apple AirPods Pro', 'qty': 2, 'price': 20999.0},
        {'customer': 'Karthik M', 'product': 'HP Pavilion Laptop', 'qty': 1, 'price': 59999.0},
        {'customer': 'Divya S', 'product': 'Boat Rockerz 550', 'qty': 4, 'price': 2199.0},
        {'customer': 'Vijay Kumar', 'product': 'Logitech Wireless Mouse', 'qty': 5, 'price': 899.0},
        {'customer': 'Anitha P', 'product': 'Sony WH-CH520 Headphones', 'qty': 2, 'price': 4499.0},
    ]

    for item in sales_data:
        customer = Customer.query.filter_by(customer_name=item['customer']).first()
        if not customer:
            customer = Customer(customer_name=item['customer'])
            db.session.add(customer)
            db.session.flush()

        product = Product.query.filter_by(name=item['product']).first()
        if not product:
            product = Product(
                name=item['product'], 
                brand='Unknown', 
                category='Accessories', 
                price=item['price'],
                stock_quantity=100,
                image_url='/static/uploads/default_placeholder.svg'
            )
            db.session.add(product)
            db.session.flush()

        if product.stock_quantity >= item['qty']:
            sale = Sale(
                customer_id=customer.id,
                product_id=product.id,
                quantity=item['qty'],
                selling_price=item['price'],
                sale_date=datetime.utcnow().date()
            )
            db.session.add(sale)
            product.stock_quantity -= item['qty']
            
    db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_supplier_columns()
        admin = Admin.query.filter_by(username='kirubakar').first()
        if not admin:
            admin = Admin.query.filter_by(username='admin').first()
        if admin:
            admin.username = 'kirubakar'
            admin.email = 'kirubakar@genzgadgets.com'
            admin.password_hash = generate_password_hash('Kiruba@123')
        else:
            admin = Admin(username='kirubakar', email='kirubakar@genzgadgets.com', password_hash=generate_password_hash('Kiruba@123'))
            db.session.add(admin)
        db.session.commit()
        seed_products()
        seed_suppliers()
        seed_customers()
        seed_purchases()
        seed_sales()
    app.run(debug=True, port=5000)
