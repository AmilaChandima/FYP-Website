import {
  BatteryMedium, CalendarCheck2, CarFront, Gauge, IdCard,
  Mail, Phone, PlugZap, Search, UserRound, UsersRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getAllBookings, getCustomers, subscribeToAdminData } from "../../services/adminData";
import { formatDateLabel, formatTime12 } from "../../utils/time";

export default function AdminCustomers() {
  const [version, setVersion] = useState(0);
  useEffect(() => subscribeToAdminData(() => setVersion((value) => value + 1)), []);
  const customers = getCustomers();
  const bookings = getAllBookings();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  useEffect(() => { if (!selectedId && customers[0]?.id) setSelectedId(customers[0].id); }, [version, selectedId, customers]);

  const filtered = customers.filter((customer) => {
    const q = search.trim().toLowerCase();
    const vehicleText = `${customer.vehicle?.make || ""} ${customer.vehicle?.model || ""} ${customer.vehicle?.registrationNumber || ""}`.toLowerCase();
    return !q || customer.name.toLowerCase().includes(q) || customer.email.toLowerCase().includes(q) || vehicleText.includes(q);
  });
  const selected = customers.find((customer) => customer.id === selectedId) || filtered[0];
  const history = useMemo(
    () => bookings.filter((booking) => booking.userId === selected?.id).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))),
    [bookings, selected]
  );
  const vehicle = selected?.vehicle || {};

  return (
    <div className="admin-page">
      <div className="admin-page-heading"><div><p>CUSTOMER DATABASE</p><h1>Registered Customers</h1></div></div>

      <div className="admin-customer-layout">
        <section className="admin-panel admin-customer-list">
          <div className="admin-search"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search customer, email or vehicle" /></div>
          <div className="admin-customer-count"><UsersRound size={18} /><span>{filtered.length} customer accounts</span></div>
          <div className="admin-customer-items">
            {filtered.map((customer) => {
              const customerBookings = bookings.filter((booking) => booking.userId === customer.id);
              return (
                <button key={customer.id} className={selected?.id === customer.id ? "active" : ""} onClick={() => setSelectedId(customer.id)}>
                  <span className="admin-customer-avatar">{customer.name.slice(0, 1).toUpperCase()}</span>
                  <span><strong>{customer.name}</strong><small>{customer.vehicle?.model || customer.email}</small></span>
                  <b>{customerBookings.length}</b>
                </button>
              );
            })}
          </div>
        </section>

        <section className="admin-panel admin-customer-detail">
          {selected ? (
            <>
              <div className="admin-customer-profile">
                <span className="admin-customer-large-avatar">{selected.name.slice(0, 1).toUpperCase()}</span>
                <div><p>REGISTERED CUSTOMER</p><h2>{selected.name}</h2><span><Mail size={15} /> {selected.email}</span></div>
              </div>
              <div className="admin-customer-facts">
                <span><small>Account created</small><strong>{new Date(selected.createdAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</strong></span>
                <span><small>Total bookings</small><strong>{history.length}</strong></span>
                <span><small>Active reservations</small><strong>{history.filter((item) => ["reserved", "scheduled", "pending"].includes(item.status)).length}</strong></span>
                <span><small>Completed visits</small><strong>{history.filter((item) => item.status === "completed").length}</strong></span>
              </div>

              <div className="admin-customer-vehicle-block">
                <div className="admin-customer-history-heading"><div><CarFront /><span><strong>Customer and EV Details</strong><small>Specifications supplied by the registered customer</small></span></div></div>
                <div className="admin-vehicle-detail-grid">
                  <span><Phone /><small>Phone number</small><strong>{selected.phone || "Not provided"}</strong></span>
                  <span><CarFront /><small>Vehicle</small><strong>{vehicle.make || "Not provided"} {vehicle.model || ""}</strong></span>
                  <span><BatteryMedium /><small>Battery capacity</small><strong>{vehicle.batteryCapacityKwh ? `${vehicle.batteryCapacityKwh} kWh` : "Not provided"}</strong></span>
                  <span><Gauge /><small>Maximum charging rate</small><strong>{vehicle.maxChargingRateKw ? `${vehicle.maxChargingRateKw} kW` : "Not provided"}</strong></span>
                  <span><PlugZap /><small>Connector type</small><strong>{vehicle.connectorType || "Not provided"}</strong></span>
                  <span><IdCard /><small>Registration number</small><strong>{vehicle.registrationNumber || "Not provided"}</strong></span>
                </div>
              </div>

              <div className="admin-customer-history-heading"><div><CalendarCheck2 /><span><strong>Booking History</strong><small>All reservations associated with this customer</small></span></div></div>
              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead><tr><th>Date</th><th>Method</th><th>Requested / scheduled time</th><th>Price</th><th>Status</th></tr></thead>
                  <tbody>
                    {history.map((booking) => <tr key={booking.id}><td>{formatDateLabel(booking.date)}</td><td><span className={`booking-type-pill ${booking.bookingType}`}>{booking.bookingType === "fixed" ? "Fixed arrival" : "Flexible"}</span></td><td>{booking.scheduledStart ? `${formatTime12(booking.scheduledStart)}–${formatTime12(booking.scheduledEnd)}` : `${formatTime12(booking.windowStart)}–${formatTime12(booking.windowEnd)}`}</td><td>Rs. {Number(booking.price).toFixed(2)}/kWh</td><td><span className={`admin-status-pill ${booking.status}`}>{booking.status}</span></td></tr>)}
                    {history.length === 0 && <tr><td colSpan="5" className="admin-empty-table">No booking history for this customer.</td></tr>}
                  </tbody>
                </table>
              </div>
            </>
          ) : <div className="admin-empty-detail"><UserRound /><p>Select a customer to view account information.</p></div>}
        </section>
      </div>
    </div>
  );
}
