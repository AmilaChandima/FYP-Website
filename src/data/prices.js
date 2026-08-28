/*
  EDIT YOUR 15-MINUTE PRICES HERE.

  There must be 96 values for one complete day:
  00:00, 00:15, 00:30 ... 23:45

  Example:
  export const todayPrices = [15, 15, 16, ...];
*/

export const todayPrices = Array.from({ length: 96 }, (_, index) => {
  const hour = index / 4;

  if (hour < 5.5) return 15;
  if (hour < 7) return 18;
  if (hour < 9) return 28 + Math.round((hour - 7) * 4);
  if (hour < 12) return 36;
  if (hour < 14) return 38 + Math.round((hour - 12) * 4);
  if (hour < 16) return 46 + Math.round((hour - 14) * 5);
  if (hour < 18.5) return 58 + Math.round((hour - 16) * 2);
  if (hour < 20) return 54;
  if (hour < 22) return 45 - Math.round((hour - 20) * 5);
  return 25;
});

export const tomorrowPrices = Array.from({ length: 96 }, (_, index) => {
  const hour = index / 4;

  if (hour < 5.5) return 14;
  if (hour < 8) return 20;
  if (hour < 11) return 32;
  if (hour < 14) return 35;
  if (hour < 17) return 48;
  if (hour < 20) return 60;
  if (hour < 22) return 42;
  return 24;
});

export function buildPriceSeries(values) {
  if (!Array.isArray(values) || values.length !== 96) {
    throw new Error("Price array must contain exactly 96 values.");
  }

  return values.map((price, index) => {
    const hours = Math.floor(index / 4);
    const minutes = (index % 4) * 15;

    return {
      slot: index + 1,
      time: `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`,
      price: Number(price),
    };
  });
}
