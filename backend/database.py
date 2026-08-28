from __future__ import annotations

import hashlib
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
import gridfs

COLOMBO = ZoneInfo('Asia/Colombo')

_CLIENT: MongoClient | None = None
_DB = None

FIXED_ARRIVAL_PRICES = [
    68,68,68,68,68,68,68,68,68,68,68,68,68,68,68,68,
    68,68,68,68,68,68,70,70,70,71,72,73,74,75,76,77,
    78,79,80,81,82,82,82,82,80,80,80,80,78,78,78,78,
    74,74,74,74,72,72,72,72,74,75,76,77,78,80,82,84,
    86,88,90,92,94,96,98,100,102,104,106,108,106,104,102,100,
    96,94,92,90,86,84,82,80,76,74,72,70,68,68,68,68,
]

DEFAULT_CHARGERS = [
    {'id': 1, 'status': 'available', 'power': 450, 'connector': 'CCS2'},
    {'id': 2, 'status': 'available', 'power': 450, 'connector': 'CCS2'},
    {'id': 3, 'status': 'charging', 'power': 450, 'connector': 'CCS2', 'progress': 78, 'remaining': '18 min'},
    {'id': 4, 'status': 'charging', 'power': 450, 'connector': 'CCS2', 'progress': 42, 'remaining': '31 min'},
    {'id': 5, 'status': 'available', 'power': 450, 'connector': 'CCS2'},
    {'id': 6, 'status': 'charging', 'power': 450, 'connector': 'CCS2', 'progress': 63, 'remaining': '22 min'},
    {'id': 7, 'status': 'available', 'power': 450, 'connector': 'CCS2'},
    {'id': 8, 'status': 'charging', 'power': 450, 'connector': 'CCS2', 'progress': 91, 'remaining': '7 min'},
    {'id': 9, 'status': 'charging', 'power': 450, 'connector': 'CCS2', 'progress': 55, 'remaining': '26 min'},
    {'id': 10, 'status': 'available', 'power': 450, 'connector': 'CCS2'},
]

DEMO_CUSTOMERS = [
    {'id':'demo-customer-1','name':'Nimal Perera','email':'customer11@gmail.com','phone':'+94 77 220 1144','vehicle':{'make':'Tesla','model':'Model 3','batteryCapacityKwh':75,'maxChargingRateKw':170,'connectorType':'CCS2','registrationNumber':'WP-CAB-1234'}},
    {'id':'demo-customer-2','name':'Tharushi Silva','email':'customer22@gmail.com','phone':'+94 71 430 2255','vehicle':{'make':'BYD','model':'Atto 3','batteryCapacityKwh':60.5,'maxChargingRateKw':88,'connectorType':'CCS2','registrationNumber':'WP-CDE-2781'}},
    {'id':'demo-customer-3','name':'Dinesh Fernando','email':'customer33@gmail.com','phone':'+94 76 541 7788','vehicle':{'make':'Hyundai','model':'Ioniq 5','batteryCapacityKwh':77.4,'maxChargingRateKw':230,'connectorType':'CCS2','registrationNumber':'SP-CAF-9912'}},
    {'id':'demo-customer-4','name':'Ayesha Jayasinghe','email':'customer44@gmail.com','phone':'+94 75 320 8841','vehicle':{'make':'Nissan','model':'Leaf','batteryCapacityKwh':62,'maxChargingRateKw':100,'connectorType':'CHAdeMO','registrationNumber':'CP-CBE-4402'}},
    {'id':'demo-customer-5','name':'Kasun Maduranga','email':'customer55@gmail.com','phone':'+94 70 662 9910','vehicle':{'make':'Kia','model':'EV6','batteryCapacityKwh':77.4,'maxChargingRateKw':240,'connectorType':'CCS2','registrationNumber':'WP-CAX-7120'}},
]


def now_colombo() -> datetime:
    return datetime.now(COLOMBO)


def date_key(value: datetime) -> str:
    return value.strftime('%Y-%m-%d')


def tomorrow_key() -> str:
    return date_key(now_colombo() + timedelta(days=1))


def sha256_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def default_today_prices() -> list[float]:
    values = []
    for index in range(96):
        hour = index / 4
        if hour < 5.5: value = 15
        elif hour < 7: value = 18
        elif hour < 9: value = 28 + round((hour - 7) * 4)
        elif hour < 12: value = 36
        elif hour < 14: value = 38 + round((hour - 12) * 4)
        elif hour < 16: value = 46 + round((hour - 14) * 5)
        elif hour < 18.5: value = 58 + round((hour - 16) * 2)
        elif hour < 20: value = 54
        elif hour < 22: value = 45 - round((hour - 20) * 5)
        else: value = 25
        values.append(float(value))
    return values


def default_tomorrow_prices() -> list[float]:
    values = []
    for index in range(96):
        hour = index / 4
        if hour < 5.5: value = 14
        elif hour < 8: value = 20
        elif hour < 11: value = 32
        elif hour < 14: value = 35
        elif hour < 17: value = 48
        elif hour < 20: value = 60
        elif hour < 22: value = 42
        else: value = 24
        values.append(float(value))
    return values


def default_station_state() -> dict[str, Any]:
    now = now_colombo()
    today = date_key(now)
    tomorrow = date_key(now + timedelta(days=1))
    return {
        'id': 'station',
        'publicToday': default_today_prices(),
        'publicTomorrow': default_tomorrow_prices(),
        'publicTodayDate': today,
        'publicTomorrowDate': tomorrow,
        'publicTomorrowAvailable': False,
        'publicTomorrowPublishedAt': None,
        'fixedBookingPrice': 78.0,
        'fixedArrivalTomorrowPrices': [float(x) for x in FIXED_ARRIVAL_PRICES],
        'flexibleBookingPrice': 62.0,
        'chargers': DEFAULT_CHARGERS,
        'draftPublicTomorrow': None,
        'draftForDate': None,
        'draftGeneratedAt': None,
        'lastAutoPublishedForDate': None,
        'lastPriceUpdate': None,
        'updatedAt': now.isoformat(),
    }


def build_revenue_data() -> dict[str, Any]:
    current = now_colombo()
    today = date_key(current)
    daily = []
    import math
    for offset in range(29, -1, -1):
        date = date_key(current - timedelta(days=offset))
        wave = math.sin((29 - offset) * 0.72) * 46000
        weekend_lift = 68000 if (29 - offset) % 7 >= 5 else 0
        amount = round(275000 + wave + weekend_lift + ((29 - offset) % 5) * 13500)
        daily.append({'date': date, 'amount': max(145000, amount)})
    today_slots = []
    for index in range(96):
        hour = index / 4
        base = 900
        if 6 <= hour < 9: base = 2800
        elif 9 <= hour < 16: base = 4300
        elif 16 <= hour < 21: base = 6500
        elif hour >= 21: base = 2600
        today_slots.append(round(base + (index % 4) * 180 + abs(math.sin(index * 0.63)) * 950))
    return {'id':'revenue', 'daily': daily, 'todaySlots': today_slots, 'generatedFor': today, 'updatedAt': current.isoformat()}


def get_db():
    global _CLIENT, _DB
    if _DB is not None:
        return _DB
    uri = os.getenv('MONGODB_URI', '').strip()
    if not uri:
        raise RuntimeError('MONGODB_URI is not configured. Copy backend/.env.example to backend/.env and add your MongoDB Atlas connection string.')
    db_name = os.getenv('MONGODB_DB', 'solarcharge').strip() or 'solarcharge'
    _CLIENT = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    _CLIENT.admin.command('ping')
    _DB = _CLIENT[db_name]
    ensure_indexes_and_seed(_DB)
    return _DB


def db_status() -> dict[str, Any]:
    try:
        db = get_db()
        db.command('ping')
        return {'connected': True, 'database': db.name, 'host': socket.gethostname()}
    except Exception as exc:
        return {'connected': False, 'database': os.getenv('MONGODB_DB', 'solarcharge'), 'error': str(exc), 'host': socket.gethostname()}


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    result = dict(doc)
    result.pop('_id', None)
    return result


def clean_many(cursor) -> list[dict[str, Any]]:
    return [_clean(doc) for doc in cursor]


def ensure_indexes_and_seed(db) -> None:
    db.customers.create_index([('id', ASCENDING)], unique=True)
    db.customers.create_index([('email', ASCENDING)], unique=True)
    db.bookings.create_index([('id', ASCENDING)], unique=True)
    db.bookings.create_index([('userId', ASCENDING), ('date', DESCENDING)])
    db.optimization_runs.create_index([('jobId', ASCENDING)], unique=True)
    db.optimization_runs.create_index([('generatedAt', DESCENDING)])

    now = now_colombo().isoformat()
    demo_hash = sha256_password('123456')
    for customer in DEMO_CUSTOMERS:
        doc = {
            **customer,
            'email': customer['email'].lower(),
            'passwordHash': demo_hash,
            'createdAt': '2026-08-27T00:00:00.000Z',
            'updatedAt': now,
            'demoAccount': True,
        }
        db.customers.update_one({'id': customer['id']}, {'$setOnInsert': doc}, upsert=True)

    if db.station_state.count_documents({'id':'station'}) == 0:
        db.station_state.insert_one(default_station_state())
    if db.revenue_state.count_documents({'id':'revenue'}) == 0:
        db.revenue_state.insert_one(build_revenue_data())


def get_station_state() -> dict[str, Any]:
    db = get_db()
    state = _clean(db.station_state.find_one({'id':'station'})) or default_station_state()
    now = now_colombo()
    today = date_key(now)
    tomorrow = date_key(now + timedelta(days=1))
    changed = False

    if state.get('publicTodayDate') != today:
        if state.get('publicTomorrowDate') == today and state.get('publicTomorrowAvailable') and isinstance(state.get('publicTomorrow'), list) and len(state['publicTomorrow']) == 96:
            state['publicToday'] = [float(v) for v in state['publicTomorrow']]
        else:
            state['publicToday'] = default_today_prices()
        state['publicTodayDate'] = today
        changed = True

    if state.get('publicTomorrowDate') != tomorrow:
        state['publicTomorrow'] = default_tomorrow_prices()
        state['publicTomorrowDate'] = tomorrow
        state['publicTomorrowAvailable'] = False
        state['publicTomorrowPublishedAt'] = None
        changed = True

    if changed:
        state['updatedAt'] = now.isoformat()
        db.station_state.replace_one({'id':'station'}, state, upsert=True)
    return state


def patch_station(patch: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    patch = dict(patch)
    patch.pop('_id', None)
    patch.pop('id', None)
    patch['updatedAt'] = now_colombo().isoformat()
    doc = db.station_state.find_one_and_update({'id':'station'}, {'$set': patch}, upsert=True, return_document=ReturnDocument.AFTER)
    return _clean(doc)


def reset_station() -> dict[str, Any]:
    db = get_db()
    state = default_station_state()
    db.station_state.replace_one({'id':'station'}, state, upsert=True)
    return state


def get_revenue_state() -> dict[str, Any]:
    db = get_db()
    state = _clean(db.revenue_state.find_one({'id':'revenue'}))
    today = date_key(now_colombo())
    if not state or state.get('generatedFor') != today:
        state = build_revenue_data()
        db.revenue_state.replace_one({'id':'revenue'}, state, upsert=True)
    return state


def customer_public(doc: dict[str, Any]) -> dict[str, Any]:
    clean = _clean(doc) or {}
    clean.pop('passwordHash', None)
    return clean


def list_customers() -> list[dict[str, Any]]:
    db = get_db()
    return [customer_public(doc) for doc in db.customers.find().sort('createdAt', ASCENDING)]


def get_customer(customer_id: str) -> dict[str, Any] | None:
    doc = get_db().customers.find_one({'id': customer_id})
    return customer_public(doc) if doc else None


def create_customer(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    email = str(payload.get('email') or '').strip().lower()
    password = str(payload.get('password') or '')
    if not email or not password:
        raise ValueError('Email and password are required.')
    now = now_colombo().isoformat()
    doc = {
        'id': str(payload.get('id') or uuid.uuid4()),
        'name': str(payload.get('name') or '').strip(),
        'phone': str(payload.get('phone') or '').strip(),
        'email': email,
        'passwordHash': sha256_password(password),
        'vehicle': payload.get('vehicle') or {},
        'createdAt': now,
        'updatedAt': now,
        'demoAccount': False,
    }
    try:
        db.customers.insert_one(doc)
    except DuplicateKeyError as exc:
        raise ValueError('An account already exists with this email address.') from exc
    return customer_public(doc)


def login_customer(email: str, password: str) -> dict[str, Any] | None:
    doc = get_db().customers.find_one({'email': str(email).strip().lower(), 'passwordHash': sha256_password(password)})
    return customer_public(doc) if doc else None


def update_customer(customer_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {'name','phone','vehicle'}
    patch = {key: payload[key] for key in allowed if key in payload}
    patch['updatedAt'] = now_colombo().isoformat()
    doc = get_db().customers.find_one_and_update({'id':customer_id}, {'$set':patch}, return_document=ReturnDocument.AFTER)
    return customer_public(doc) if doc else None


def list_bookings(user_id: str | None = None, date: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if user_id: query['userId'] = user_id
    if date: query['date'] = date
    return clean_many(get_db().bookings.find(query).sort('createdAt', DESCENDING))


def _minutes(value: str | None) -> int | None:
    if not value: return None
    try:
        h, m = str(value).split(':')[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def assign_fixed_charger(booking: dict[str, Any]) -> int:
    start = _minutes(booking.get('scheduledStart') or booking.get('arrivalTime'))
    end = _minutes(booking.get('scheduledEnd'))
    if start is None or end is None:
        raise ValueError('Fixed booking is missing a valid scheduled period.')
    existing = list_bookings(date=booking.get('date'))
    for charger_id in range(1, 11):
        conflict = False
        for item in existing:
            if item.get('status') not in {'reserved','scheduled','completed'} or int(item.get('chargerId') or 0) != charger_id:
                continue
            b0 = _minutes(item.get('scheduledStart') or item.get('arrivalTime'))
            b1 = _minutes(item.get('scheduledEnd'))
            if b0 is not None and b1 is not None and _overlaps(start, end, b0, b1):
                conflict = True
                break
        if not conflict:
            return charger_id
    raise ValueError('All 10 chargers are already reserved during part of this charging period. Select another arrival time.')


def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    booking = dict(payload)
    booking.pop('_id', None)
    booking['id'] = str(booking.get('id') or uuid.uuid4())
    now = now_colombo().isoformat()
    booking.setdefault('createdAt', now)
    booking['updatedAt'] = now
    if booking.get('bookingType') == 'fixed':
        booking['chargerId'] = assign_fixed_charger(booking)
        booking['status'] = 'reserved'
        booking['notification'] = f"Confirmed: arrive tomorrow at {booking.get('arrivalTime')}. Charger {int(booking['chargerId']):02d} is reserved until {booking.get('scheduledEnd')}."
        booking['notifiedAt'] = now
    try:
        db.bookings.insert_one(booking)
    except DuplicateKeyError as exc:
        raise ValueError('This booking has already been saved.') from exc
    booking.pop('_id', None)
    return booking


def patch_booking(booking_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    patch = dict(patch)
    patch.pop('_id', None); patch.pop('id', None)
    patch['updatedAt'] = now_colombo().isoformat()
    doc = get_db().bookings.find_one_and_update({'id':booking_id}, {'$set':patch}, return_document=ReturnDocument.AFTER)
    return _clean(doc)


def upsert_optimization_result(result: dict[str, Any], machine_name: str | None = None) -> None:
    db = get_db()
    job_id = str(result.get('jobId') or '')
    if not job_id: return
    doc = {
        'jobId': job_id,
        'targetDate': result.get('targetDate'),
        'generatedAt': result.get('generatedAt') or now_colombo().isoformat(),
        'result': result,
        'machineName': machine_name or socket.gethostname(),
        'updatedAt': now_colombo().isoformat(),
    }
    db.optimization_runs.update_one({'jobId':job_id}, {'$set':doc}, upsert=True)


def get_optimization_result(job_id: str) -> dict[str, Any] | None:
    doc = get_db().optimization_runs.find_one({'jobId':job_id})
    return (doc or {}).get('result') if doc else None


def latest_optimization_result() -> dict[str, Any] | None:
    doc = get_db().optimization_runs.find_one(sort=[('generatedAt', DESCENDING)])
    return (doc or {}).get('result') if doc else None


def optimization_history(limit: int = 10) -> list[dict[str, Any]]:
    docs = get_db().optimization_runs.find().sort('generatedAt', DESCENDING).limit(max(1, min(limit, 50)))
    rows = []
    for doc in docs:
        parsed = doc.get('result') or {}
        metrics = parsed.get('metrics') or {}
        rows.append({
            'jobId': parsed.get('jobId'),
            'targetDate': parsed.get('targetDate'),
            'generatedAt': parsed.get('generatedAt'),
            'priceAverageLKRkWh': metrics.get('priceAverageLKRkWh'),
            'forecastTotalProfitLKR': metrics.get('forecastTotalProfitLKR'),
            'forecastTotalRevenueLKR': metrics.get('forecastTotalRevenueLKR'),
            'machineName': doc.get('machineName'),
        })
    return rows


def apply_optimizer_notifications(result: dict[str, Any]) -> dict[str, int]:
    notifications = result.get('elasticNotifications') if isinstance(result, dict) else []
    web = [item for item in (notifications or []) if str(item.get('user_id') or '').startswith('WEB-')]
    db = get_db()
    delivered = 0
    unmatched = 0
    job_id = str(result.get('jobId') or '')
    for item in web:
        booking_id = str(item.get('user_id'))[4:]
        previous = _clean(db.bookings.find_one({'id':booking_id, 'bookingType':'flexible'}))
        if not previous:
            unmatched += 1
            continue
        start = str(item.get('assigned_arrival_and_plugin_time') or '')[:5]
        end = str(item.get('expected_charging_completion_time') or '')[:5]
        charger = int(float(item.get('assigned_charger_pile') or 0)) or None
        try: tariff = float(item.get('final_elastic_tariff_LKR_kWh'))
        except Exception: tariff = previous.get('price')
        message = str(item.get('notification_message') or '').strip() or previous.get('notification')
        is_new = previous.get('optimizerJobId') != job_id or previous.get('notification') != message or previous.get('notificationSource') != 'elastic_user_notifications.csv'
        delivered_at = now_colombo().isoformat()
        patch = {
            'status':'scheduled',
            'scheduledStart': start or previous.get('scheduledStart'),
            'scheduledEnd': end or previous.get('scheduledEnd'),
            'chargerId': charger,
            'price': tariff,
            'notification': message,
            'notifiedAt': delivered_at if is_new else previous.get('notifiedAt'),
            'notificationReadAt': None if is_new else previous.get('notificationReadAt'),
            'optimizerJobId': job_id,
            'optimizerControllerEvId': item.get('user_id'),
            'notificationSource':'elastic_user_notifications.csv',
            'updatedAt': delivered_at,
        }
        db.bookings.update_one({'id':booking_id}, {'$set':patch})
        delivered += 1
    return {'deliveredCount':delivered, 'unmatchedCount':unmatched, 'totalWebsiteNotifications':len(web)}


def migrate_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    imported = {'customers':0,'bookings':0,'station':False,'revenue':False}
    for account in payload.get('accounts') or []:
        email = str(account.get('email') or '').strip().lower()
        if not email or not account.get('id'): continue
        doc = dict(account); doc.pop('_id', None); doc['email'] = email
        # Demo accounts keep their canonical MongoDB login credentials, but any
        # profile/vehicle edits made in the previous browser version are preserved.
        if doc.get('demoAccount') or str(doc.get('id','')).startswith('demo-customer-'):
            demo_patch = {key: doc.get(key) for key in ('name','phone','vehicle') if key in doc}
            demo_patch['updatedAt'] = doc.get('updatedAt') or now_colombo().isoformat()
            db.customers.update_one({'id':doc['id']}, {'$set':demo_patch})
            imported['customers'] += 1
            continue
        if not doc.get('passwordHash'):
            continue
        db.customers.update_one({'$or':[{'id':doc['id']},{'email':email}]}, {'$setOnInsert':doc}, upsert=True)
        imported['customers'] += 1
    for booking in payload.get('bookings') or []:
        if not booking.get('id'): continue
        doc = dict(booking); doc.pop('_id', None)
        db.bookings.update_one({'id':doc['id']}, {'$setOnInsert':doc}, upsert=True)
        imported['bookings'] += 1

    marker = db.app_meta.find_one({'id':'legacy-localstorage-migration'})
    if not marker:
        station = payload.get('station')
        if isinstance(station, dict) and len(station.get('publicToday') or []) == 96:
            safe = default_station_state()
            for key in safe.keys():
                if key in station and key != 'id': safe[key] = station[key]
            safe['id'] = 'station'; safe['updatedAt'] = now_colombo().isoformat()
            db.station_state.replace_one({'id':'station'}, safe, upsert=True)
            imported['station'] = True
        revenue = payload.get('revenue')
        if isinstance(revenue, dict) and revenue.get('daily') and revenue.get('todaySlots'):
            doc = dict(revenue); doc['id']='revenue'; doc['updatedAt']=now_colombo().isoformat()
            db.revenue_state.replace_one({'id':'revenue'}, doc, upsert=True)
            imported['revenue'] = True
        db.app_meta.update_one({'id':'legacy-localstorage-migration'}, {'$set':{'id':'legacy-localstorage-migration','completedAt':now_colombo().isoformat()}}, upsert=True)
    return imported


def store_optimization_file(job_id: str, filename: str, data: bytes) -> None:
    db = get_db()
    fs = gridfs.GridFS(db, collection='optimizer_files')
    for existing in fs.find({'metadata.jobId': job_id, 'filename': filename}):
        fs.delete(existing._id)
    fs.put(data, filename=filename, metadata={'jobId': job_id, 'storedAt': now_colombo().isoformat()})


def fetch_optimization_file(job_id: str, filename: str) -> bytes | None:
    db = get_db()
    fs = gridfs.GridFS(db, collection='optimizer_files')
    item = fs.find_one({'metadata.jobId': job_id, 'filename': filename}, sort=[('uploadDate', DESCENDING)])
    return item.read() if item else None


def list_optimization_files(job_id: str) -> list[str]:
    db = get_db()
    fs = gridfs.GridFS(db, collection='optimizer_files')
    names = {item.filename for item in fs.find({'metadata.jobId': job_id})}
    return sorted(names)
