import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import RunsPage from "./pages/RunsPage.jsx";
import RunDashboard from "./pages/RunDashboard.jsx";
import RunPatches from "./pages/RunPatches.jsx";  // 👈 ADD THIS

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/runs" replace />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDashboard />} />
        <Route path="/runs/:runId/patches" element={<RunPatches />} />  {/* 👈 ADD THIS */}
      </Routes>
    </BrowserRouter>
  );
}