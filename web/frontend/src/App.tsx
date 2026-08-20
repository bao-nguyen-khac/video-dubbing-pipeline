import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import JobListPage from "./pages/JobListPage";
import JobDetailPage from "./pages/JobDetailPage";
import PublishPage from "./pages/PublishPage";
import DownloadsPage from "./pages/DownloadsPage";
import GenerateVideoPage from "./pages/GenerateVideoPage";
import ScriptToVideoPage from "./pages/ScriptToVideoPage";
import ConfirmDialog from "./components/ConfirmDialog";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import "./App.css";

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<HomePage />} />
            <Route path="/generate" element={<GenerateVideoPage />} />
            <Route path="/script-to-video" element={<ScriptToVideoPage />} />
            <Route path="/jobs" element={<JobListPage />} />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
            <Route path="/downloads" element={<DownloadsPage />} />
            <Route path="/publish" element={<PublishPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <ConfirmDialog />
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  );
}
