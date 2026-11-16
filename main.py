import json, os, sqlite3, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
BOOKS = json.loads((ROOT / 'data' / 'books.json').read_text(encoding='utf-8'))
app = FastAPI(title='PageTurner Books API', version='1.1.0')
app.mount('/assets', StaticFiles(directory=ROOT / 'public' / 'assets'), name='assets')


def db():
    """Local SQLite for development; hosted SQLite-compatible libSQL on Vercel."""
    remote_url = os.getenv('TURSO_DATABASE_URL')
    if remote_url:
        try:
            import libsql
        except ImportError as exc:
            raise HTTPException(503, 'Install the libsql Python package.') from exc
        token = os.getenv('TURSO_AUTH_TOKEN')
        if not token:
            raise HTTPException(503, 'TURSO_AUTH_TOKEN is missing.')
        return libsql.connect(database=remote_url, auth_token=token)
    db_path = os.getenv('SQLITE_PATH', str(ROOT / 'pageturner.db'))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def rows_as_dicts(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], sqlite3.Row):
        return [dict(row) for row in rows]
    cols = [item[0] for item in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


def init_db():
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
            category TEXT NOT NULL, price INTEGER NOT NULL CHECK(price > 0),
            pages INTEGER, image TEXT, is_seed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, customer_name TEXT NOT NULL, email TEXT NOT NULL,
            phone TEXT NOT NULL, delivery_address TEXT NOT NULL, items TEXT NOT NULL,
            total_lkr INTEGER NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'cash_on_delivery',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        for b in BOOKS:
            conn.execute('''INSERT OR IGNORE INTO books
                (id,title,author,category,price,pages,image,is_seed)
                VALUES(?,?,?,?,?,?,?,1)''',
                (b['id'], b['title'], b['author'], b['category'], b['price'], b.get('pages'), b.get('image')))


class NewBook(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    author: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    price: int = Field(gt=0, le=10000000)
    image: str | None = None

class Customer(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(min_length=7, max_length=30)
    address: str = Field(min_length=8, max_length=500)

class OrderRequest(BaseModel):
    customer: Customer
    items: list[dict] = Field(min_length=1, max_length=30)


@app.get('/')
def home():
    return FileResponse(ROOT / 'public' / 'index.html')

@app.get('/api/health')
def health():
    try:
        init_db()
        with db() as conn:
            count = conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]
        return {'ok': True, 'database': 'sqlite', 'books': count}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f'Database connection failed: {type(exc).__name__}')

@app.get('/api/books')
def list_books():
    init_db()
    with db() as conn:
        cur = conn.execute('''SELECT id,title,author,category,price,pages,image,is_seed
            FROM books ORDER BY is_seed DESC, created_at DESC''')
        return rows_as_dicts(cur)

@app.post('/api/books')
def add_book(book: NewBook, x_admin_key: str | None = Header(default=None)):
    expected = os.getenv('ADMIN_KEY')
    if not expected or not x_admin_key or x_admin_key != expected:
        raise HTTPException(403, 'Book management is disabled or the admin key is incorrect.')
    init_db()
    book_id = 'custom-' + uuid.uuid4().hex[:16]
    with db() as conn:
        conn.execute('''INSERT INTO books(id,title,author,category,price,image,is_seed)
            VALUES(?,?,?,?,?,?,0)''',
            (book_id, book.title.strip(), book.author.strip(), book.category.strip(), book.price, book.image))
    return {'id': book_id, **book.model_dump()}

@app.delete('/api/books/{book_id}')
def delete_book(book_id: str, x_admin_key: str | None = Header(default=None)):
    expected = os.getenv('ADMIN_KEY')
    if not expected or not x_admin_key or x_admin_key != expected:
        raise HTTPException(403, 'Book management is disabled or the admin key is incorrect.')
    init_db()
    with db() as conn:
        result = conn.execute('DELETE FROM books WHERE id=? AND is_seed=0', (book_id,))
        if result.rowcount == 0:
            raise HTTPException(404, 'Custom book not found. Original catalogue books cannot be deleted.')
    return {'deleted': True}

@app.post('/api/orders')
def create_order(order: OrderRequest):
    init_db()
    ids = list(dict.fromkeys(str(i.get('id', '')) for i in order.items))
    if not ids or any(not x for x in ids):
        raise HTTPException(400, 'Invalid cart.')
    marks = ','.join('?' for _ in ids)
    with db() as conn:
        cur = conn.execute(f'SELECT id,title,price FROM books WHERE id IN ({marks})', tuple(ids))
        by_id = {r['id']: r for r in rows_as_dicts(cur)}
        clean, total = [], 0
        for item in order.items:
            bid, qty = str(item.get('id', '')), item.get('qty')
            if bid not in by_id or type(qty) is not int or qty < 1 or qty > 20:
                raise HTTPException(400, 'Your cart contains an unavailable book or invalid quantity.')
            b = by_id[bid]
            line = b['price'] * qty
            total += line
            clean.append({'id': bid, 'title': b['title'], 'unit_price_lkr': b['price'], 'quantity': qty, 'line_total_lkr': line})
        order_id = 'PT-' + uuid.uuid4().hex[:10].upper()
        conn.execute('''INSERT INTO orders
            (id,customer_name,email,phone,delivery_address,items,total_lkr)
            VALUES(?,?,?,?,?,?,?)''',
            (order_id, order.customer.name, order.customer.email, order.customer.phone,
             order.customer.address, json.dumps(clean, ensure_ascii=False), total))
    return {'order_id': order_id, 'total_lkr': total, 'status': 'pending', 'payment_method': 'cash_on_delivery'}

@app.get('/api/admin/orders')
def admin_orders(x_admin_key: str | None = Header(default=None)):
    expected = os.getenv('ADMIN_KEY')
    if not expected or not x_admin_key or x_admin_key != expected:
        raise HTTPException(403, 'Admin key is incorrect.')
    init_db()
    with db() as conn:
        cur = conn.execute('''SELECT id,customer_name,email,phone,delivery_address,items,total_lkr,
            payment_method,status,created_at FROM orders ORDER BY created_at DESC LIMIT 200''')
        orders = rows_as_dicts(cur)
        for order in orders:
            order['items'] = json.loads(order['items'])
        return orders
