## PROMPT FOR AI AGENT

**Role:** You are a Senior Django Developer with 5+ years of experience. Your task is to implement product upload and inventory management functionality.

**Project Context:**
Product inventory management system for tracking product arrivals and sales (on Ozon and other platforms). Working with Excel/CSV spreadsheets.

**Tech Stack:**
- Python 3.x
- Django (latest stable version)
- MySQL (with Django ORM)
- Structure: Django project + "web" app

---

### STAGE 1: Product Upload and Inventory

**Task:** Implement data upload from Excel/CSV files and storage in the database.

#### 1. DATA MODELS

Create the following models in `web/models.py`:

**Product Model (Product Inventory):**
```
Fields:
- article (CharField): Product article/SKU (unique)
- name (CharField): Product name
- quantity (IntegerField): Quantity in stock
- purchase_price (DecimalField): Purchase cost
- delivery_cost (DecimalField): Delivery cost
- cost_price (DecimalField): Cost price (calculated: purchase_price + delivery_cost)
- status (CharField with choices): 
  * 'in_stock' — In Stock
  * 'in_sale' — In Sale
  * 'sold' — Sold
- created_at (DateTimeField): Record creation date
- updated_at (DateTimeField): Record update date
```

**SaleRecord Model (Sales Records):**
```
Fields:
- product (ForeignKey to Product): Related product
- article (CharField): Article/SKU (duplicated for convenience)
- name (CharField): Name
- sale_type (CharField with choices):
  * 'ozon' — Ozon Sale
  * 'free' — Free Sale
- income (DecimalField): Income (sale price)
- profit (DecimalField): Profit (calculated: income - cost_price)
- sale_date (DateField): Sale date
- created_at (DateTimeField): Creation date
```

#### 2. UPLOAD FUNCTIONALITY

**View for uploading supply (`web/views.py`):**
- Create view `upload_supply` (function-based or class-based)
- Handle POST request with file (Excel/CSV)
- Parse file (use pandas or openpyxl)
- For each row:
  * Extract: article, name, purchase_price, delivery_cost, quantity
  * Calculate cost_price = purchase_price + delivery_cost
  * Create Product record with status 'in_stock'
- Save all records to database
- Return response: number of uploaded products / errors

**View for uploading sales:**
- Create view `upload_sales`
- Accepts file + parameter sale_type ('ozon' or 'free')
- Parses file with fields: article, name, income, quantity
- For each sale:
  * Find Product by article
  * Change status to 'in_sale' or 'sold'
  * Create SaleRecord with profit calculation: profit = income - cost_price
- Handle cases when product is not in database

#### 3. URLS

Create in `web/urls.py`:
```python
path('upload/supply/', views.upload_supply, name='upload_supply'),
path('upload/sales/', views.upload_sales, name='upload_sales'),
path('products/', views.product_list, name='product_list'),  # product list
```

#### 4. FORMS

Create Django Form or use standard mechanisms for:
- File upload (FileField with extension validation: .xlsx, .xls, .csv)

#### 5. TEMPLATES

Create HTML templates using the provided color scheme:

**Colors:**
- Primary accent: `#FC4445` (red)
- Secondary: `#3FEEE6` (turquoise)
- Additional: `#55BCC9` (blue)
- Light: `#97CAEF`
- Background: `#CAFAFE`

**Pages:**
1. `upload_supply.html` — supply upload form
2. `upload_sales.html` — sales upload form (with type selection: Ozon/Free)
3. `product_list.html` — product list display

**UI Requirements:**
- Responsive design (bootstrap or pure CSS)
- Buttons with color `#FC4445`
- Headers/accents with `#3FEEE6` or `#55BCC9`
- Page background `#CAFAFE`
- Tables with readable formatting

#### 6. DATA EXAMPLES

**"Supply" file format:**
```
Article | Name | Purchase Cost | Delivery | Cost Price | Quantity
JGET1001GM190 | TT Gear Motor 1:90 | 30 | 15 | 45 | 5
```

**"Free Sale" file format:**
```
Article | Name | Income | Quantity
JGET1001GM190 | TT Gear Motor 1:90 | 55 | 1
```

**"Product Inventory" format (database display):**
```
Article | Name | Status | Cost Price | Income | Profit | Sale Date
JGET1001GM190 | ... | In Stock | 45 | - | - | -
JGET1001GM190 | ... | In Sale | 45 | 55 | 10 | 10.04.2026
JGET1001GM190 | ... | Sold | 45 | 35 | -10 | 11.04.2026
```

---

### TECHNICAL REQUIREMENTS:

1. **Validation:**
   - Check for empty required fields
   - Data type validation (numbers, strings)
   - Error handling during file parsing

2. **Security:**
   - CSRF protection on forms
   - Uploaded file validation

3. **Code:**
   - Follow Django best practices
   - Use Django ORM
   - Logic separation (views, forms, models)
   - Comments for complex code sections

4. **Dependencies:**
   - Add to requirements.txt: pandas, openpyxl (for Excel handling)

---

### EXPECTED RESULT:

1. Working models.py with migrations
2. Working views.py with upload logic
3. forms.py with upload forms
4. HTML templates with design in specified colors
5. urls.py with correct routes
6. Instructions for running and testing

**Do NOT implement at this stage:**
- Data export (Stage 2)
- Complex analytics
- API
- Authorization/authentication (unless required)

---

**Start implementation with creating models, then forms, then views, and finally templates. After each step (IMPORTANT!), show the code and explain the logic.**

---