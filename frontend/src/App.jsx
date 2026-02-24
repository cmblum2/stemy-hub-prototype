import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import RunsPage from "./pages/RunsPage.jsx";
import RunDashboard from "./pages/RunDashboard.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/runs" />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}