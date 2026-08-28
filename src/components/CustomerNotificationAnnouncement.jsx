import { BellRing, CalendarClock, CheckCircle2, PlugZap, Tag } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getBookings, subscribeToBookings } from "../services/bookings";
import { formatDateLabel, formatTime12 } from "../utils/time";

export default function CustomerNotificationAnnouncement() {
  const { user, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);

  useEffect(() => subscribeToBookings(() => setVersion((value) => value + 1)), []);

  const latest = useMemo(() => {
    if (!isLoggedIn || !user?.id) return null;
    return getBookings()
      .filter((booking) =>
        booking.userId === user.id
        && booking.bookingType === "flexible"
        && booking.status === "scheduled"
        && booking.notificationSource === "elastic_user_notifications.csv"
        && booking.notification
      )
      .sort((a, b) => String(b.notifiedAt || b.updatedAt || "").localeCompare(String(a.notifiedAt || a.updatedAt || "")))[0] || null;
  }, [isLoggedIn, user?.id, version]);

  if (!latest) return null;

  return (
    <section className="customer-main-announcement" role="status" aria-live="polite">
      <div className="customer-main-announcement-inner">
        <div className="announcement-bell"><BellRing /></div>
        <div className="announcement-copy">
          <span><CheckCircle2 size={15} /> IMPORTANT CHARGING ANNOUNCEMENT</span>
          <h2>Your flexible charging time is confirmed</h2>
          <p>{latest.notification}</p>
          <div className="announcement-details">
            <small><CalendarClock /> {formatDateLabel(latest.date)} · {formatTime12(latest.scheduledStart)}–{formatTime12(latest.scheduledEnd)}</small>
            <small><PlugZap /> Charger {latest.chargerId || "—"}</small>
            <small><Tag /> Rs. {Number(latest.price || 0).toFixed(2)}/kWh</small>
          </div>
        </div>
        <button type="button" onClick={() => navigate("/booking")}>View My Booking</button>
      </div>
    </section>
  );
}
