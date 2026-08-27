import os

app_path = r'c:\Users\work\Desktop\gen Z gadgets\GENZ_GADGET_HUB_50_PERCENT\app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

# Fix 1: description missing
old_description = '''        category = request.form.get('category', '').strip()
        try:'''
new_description = '''        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        try:'''

# Fix 2: name unused in delete_supplier
old_delete_supplier = '''def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    name = supplier.company_name
    db.session.delete(supplier)'''
new_delete_supplier = '''def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)'''

# Fix 3: import json duplicate
old_dashboard = '''    # Analytics Data
    import json
    
    category_counts = {}'''
new_dashboard = '''    # Analytics Data
    
    category_counts = {}'''

if old_description in app_content:
    app_content = app_content.replace(old_description, new_description)
    print("Fixed description missing")
    
if old_delete_supplier in app_content:
    app_content = app_content.replace(old_delete_supplier, new_delete_supplier)
    print("Fixed unused name in delete_supplier")
    
if old_dashboard in app_content:
    app_content = app_content.replace(old_dashboard, new_dashboard)
    print("Fixed duplicate import json")
    
with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
