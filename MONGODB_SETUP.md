# SolarCharge Shared MongoDB Setup

This version is the **pre-Option-A website** upgraded to use one central MongoDB database while keeping the optimizer local on every group member's laptop.

## Architecture

Each member runs locally:

- React/Vite: `http://localhost:5173`
- FastAPI: `http://127.0.0.1:8000`
- Python/Pyomo/Gurobi optimizer: local laptop only

All FastAPI instances connect to the same MongoDB database:

```text
Member A browser -> Member A FastAPI/Gurobi --\
Member B browser -> Member B FastAPI/Gurobi ----> MongoDB Atlas
Member C browser -> Member C FastAPI/Gurobi --/
```

Shared through MongoDB:

- customer accounts and EV details
- bookings
- optimizer-generated customer notifications + read/unread state
- public price schedules
- fixed-arrival booking prices
- flexible booking reference price
- charger states
- revenue demo data
- parsed optimization results/history
- key optimizer result CSV/TXT files via MongoDB GridFS, so another group laptop can download them

Local to the laptop that runs an optimization:

- uploaded optimizer input files
- generated Excel input copy
- Gurobi execution
- the actual Gurobi process and local run workspace

Key result CSV/TXT files are also copied to MongoDB GridFS after a successful run for shared download access.

## 1. Create MongoDB Atlas database

1. Go to https://www.mongodb.com/atlas
2. Create a project, e.g. `SolarCharge FYP`.
3. Create an M0/free cluster if available for your account.
4. Create a database user with a strong password.
5. Under **Network Access**, either:
   - add each group member's public IP address, or
   - for a short university demo, temporarily allow `0.0.0.0/0` and use a strong database password.
6. Open **Connect -> Drivers -> Python** and copy the connection string.

Example:

```text
mongodb+srv://solarcharge_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

If the password contains characters such as `@`, `:`, `/`, `%`, `#`, URL-encode them or create a password without special URL characters for the demo.

## 2. Configure this project

Inside `backend/` copy:

```text
.env.example -> .env
```

Edit `backend/.env`:

```env
MONGODB_URI=mongodb+srv://solarcharge_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=solarcharge
```

**Every group member must use the same `MONGODB_URI` and `MONGODB_DB`.**

Do not commit `.env` to GitHub. It is already ignored by `.gitignore`.

## 3. Existing customer data migration

The first time the upgraded frontend starts, it looks for data from the old browser-only version:

- `solarcharge_accounts_v1`
- `solarcharge_bookings_v1`
- `solarcharge_station_data_v1`
- `solarcharge_revenue_v1`

It sends any available data once to MongoDB.

The five demo accounts are seeded automatically by FastAPI even if no old browser data exists:

| Customer | Email | Password |
| --- | --- | --- |
| Nimal Perera | `customer11@gmail.com` | `123456` |
| Tharushi Silva | `customer22@gmail.com` | `123456` |
| Dinesh Fernando | `customer33@gmail.com` | `123456` |
| Ayesha Jayasinghe | `customer44@gmail.com` | `123456` |
| Kasun Maduranga | `customer55@gmail.com` | `123456` |

Any newly registered customer is immediately stored in MongoDB and is visible to all group members.

## 4. Check the connection

Start the backend and open:

```text
http://127.0.0.1:8000/api/health
```

A successful response includes:

```json
{
  "status": "ok",
  "database": {
    "connected": true,
    "database": "solarcharge"
  }
}
```

You can also open:

```text
http://127.0.0.1:8000/api/database/status
```

## 5. Multi-laptop behavior

Example:

1. Member A creates a customer account or booking.
2. It is stored in MongoDB.
3. Member B's website refreshes shared data automatically within a few seconds.
4. Member B can generate `Primary_Elastic_EV_Users.xlsx` from the same shared bookings.
5. Member B runs Gurobi locally.
6. Parsed optimization results are saved to MongoDB.
7. Member A can then open the same optimization result charts from their admin dashboard.
8. Publishing tomorrow price and elastic notifications updates MongoDB, so every member/customer sees the same result.

The full optimizer run workspace remains on the laptop where that run was executed. After a successful run, the parsed result and the key CSV/TXT/log outputs are also copied to MongoDB/GridFS so other group laptops can review and download them.
