# SolarCharge — Shared MongoDB + Local Optimizer Version

This project is based on the final **pre-Option-A** SolarCharge website. Its UI and workflow are preserved, but the browser-only data layer has been replaced by a central MongoDB database.

## Key design

- React/Vite frontend runs locally on each laptop.
- FastAPI runs locally on each laptop.
- Python/Pyomo/Gurobi optimization runs locally on whichever laptop starts the optimization.
- All group members use the same MongoDB database.
- Customers, bookings, notifications, prices, charger states and optimization result history synchronize across group laptops.
- The Gurobi run workspace remains local; parsed results and key downloadable result files are copied to MongoDB for shared access.

## First-time setup

1. Read `MONGODB_SETUP.md` and configure `backend/.env`.
2. Install Node.js, Python and Gurobi.
3. Run:

```bat
setup.bat
```

4. Optional: verify MongoDB from the backend virtual environment:

```bat
cd backend
.venv\Scripts\activate
python check_database.py
cd ..
```

5. Start the application:

```bat
run.bat
```

Customer website:

```text
http://localhost:5173
```

Admin:

```text
http://localhost:5173/admin
```

Admin credentials:

```text
Username: admin
Password: admin1234
```

## Demo customer credentials

All demo customers use password `123456`:

- `customer11@gmail.com`
- `customer22@gmail.com`
- `customer33@gmail.com`
- `customer44@gmail.com`
- `customer55@gmail.com`

## Optimizer workflow

1. Customer bookings are stored in MongoDB.
2. Admin -> Customer Bookings reads the shared bookings.
3. Generate `Primary_Elastic_EV_Users.xlsx` locally.
4. Upload the four optimizer files.
5. Run Gurobi locally.
6. Parsed optimization result is copied to MongoDB for shared viewing/history.
7. Click **Publish Tomorrow Price & Notify Flexible Customers**.
8. Public price + customer flexible notifications are saved centrally in MongoDB.

## GitHub

See `GITHUB_SETUP.md`.
