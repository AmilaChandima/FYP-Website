import { useEffect, useMemo, useState } from "react";

const TIME_ZONE = "Asia/Colombo";

function getTimeParts(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);

  return Object.fromEntries(
    parts.filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)])
  );
}

function slotTime(index) {
  const minutes = (index % 96) * 15;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

export function useCurrentPrice(prices) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return useMemo(() => {
    const { hour = 0, minute = 0, second = 0 } = getTimeParts(now);
    const slotIndex = Math.floor((hour * 60 + minute) / 15);

    return {
      currentPrice: Number(prices[slotIndex]),
      slotIndex,
      startTime: slotTime(slotIndex),
      endTime: slotTime(slotIndex + 1),
      clock: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`,
    };
  }, [now, prices]);
}
