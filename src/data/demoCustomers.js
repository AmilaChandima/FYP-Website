export const DEMO_PASSWORD = "123456";
export const DEMO_PASSWORD_HASH = "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92";

const DEMO_CUSTOMERS = [
  {
    id: "demo-customer-1",
    name: "Nimal Perera",
    email: "customer11@gmail.com",
    phone: "+94 77 220 1144",
    vehicle: { make: "Tesla", model: "Model 3", batteryCapacityKwh: 75, maxChargingRateKw: 170, connectorType: "CCS2", registrationNumber: "WP-CAB-1234" },
  },
  {
    id: "demo-customer-2",
    name: "Tharushi Silva",
    email: "customer22@gmail.com",
    phone: "+94 71 430 2255",
    vehicle: { make: "BYD", model: "Atto 3", batteryCapacityKwh: 60.5, maxChargingRateKw: 88, connectorType: "CCS2", registrationNumber: "WP-CDE-2781" },
  },
  {
    id: "demo-customer-3",
    name: "Dinesh Fernando",
    email: "customer33@gmail.com",
    phone: "+94 76 541 7788",
    vehicle: { make: "Hyundai", model: "Ioniq 5", batteryCapacityKwh: 77.4, maxChargingRateKw: 230, connectorType: "CCS2", registrationNumber: "SP-CAF-9912" },
  },
  {
    id: "demo-customer-4",
    name: "Ayesha Jayasinghe",
    email: "customer44@gmail.com",
    phone: "+94 75 320 8841",
    vehicle: { make: "Nissan", model: "Leaf", batteryCapacityKwh: 62, maxChargingRateKw: 100, connectorType: "CHAdeMO", registrationNumber: "CP-CBE-4402" },
  },
  {
    id: "demo-customer-5",
    name: "Kasun Maduranga",
    email: "customer55@gmail.com",
    phone: "+94 70 662 9910",
    vehicle: { make: "Kia", model: "EV6", batteryCapacityKwh: 77.4, maxChargingRateKw: 240, connectorType: "CCS2", registrationNumber: "WP-CAX-7120" },
  },
];

export function getDemoCustomerAccounts() {
  return DEMO_CUSTOMERS.map((customer) => ({
    ...customer,
    passwordHash: DEMO_PASSWORD_HASH,
    createdAt: "2026-08-27T00:00:00.000Z",
    updatedAt: "2026-08-27T00:00:00.000Z",
    demoAccount: true,
  }));
}

// Demo customers are seeded by the FastAPI backend into MongoDB.
export function ensureDemoCustomerAccounts() {
  return getDemoCustomerAccounts();
}
