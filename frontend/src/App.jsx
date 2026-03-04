import { BrowserRouter, Routes, Route } from "react-router-dom";
import VoiceChat from "./pages/VoiceChat";
import ManualPatches from "./pages/ManualPatches";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<VoiceChat />} />
        <Route path="/manual" element={<ManualPatches />} />
      </Routes>
    </BrowserRouter>
  );
}