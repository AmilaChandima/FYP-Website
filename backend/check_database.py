from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')

from database import db_status, get_db

status = db_status()
print('MongoDB status:', status)
if not status.get('connected'):
    raise SystemExit(1)

db = get_db()
print('Customers:', db.customers.count_documents({}))
print('Bookings:', db.bookings.count_documents({}))
print('Optimization runs:', db.optimization_runs.count_documents({}))
print('Station state:', db.station_state.count_documents({'id': 'station'}))
print('Revenue state:', db.revenue_state.count_documents({'id': 'revenue'}))
