import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import { AdminAuthProvider } from "./context/AdminAuthContext";
import { StationDataProvider } from "./context/StationDataContext";
import { ensureDemoData } from "./services/adminData";
import { migratePreviousBrowserDataToMongo } from "./services/databaseMigration";
import "./styles.css";

migratePreviousBrowserDataToMongo().finally(() => ensureDemoData());

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <StationDataProvider>
        <AuthProvider>
          <AdminAuthProvider>
            <App />
          </AdminAuthProvider>
        </AuthProvider>
      </StationDataProvider>
    </BrowserRouter>
  </React.StrictMode>
);
