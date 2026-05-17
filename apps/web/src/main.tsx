import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./console/theme/console-tokens.css";
import "./console/console.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
