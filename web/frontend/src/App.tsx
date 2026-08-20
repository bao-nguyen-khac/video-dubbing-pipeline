import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import JobListPage from "./pages/JobListPage";
import JobDetailPage from "./pages/JobDetailPage";
import DownloadsPage from "./pages/DownloadsPage";
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
            <Route path="/jobs" element={<JobListPage />} />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
            <Route path="/downloads" element={<DownloadsPage />} />

            {/* Các module tạm ẩn trên nhánh này -> chuyển hướng về trang chính */}
            <Route path="/generate" element={<Navigate to="/" replace />} />
            <Route path="/script-to-video" element={<Navigate to="/" replace />} />
            <Route path="/publish" element={<Navigate to="/" replace />} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <ConfirmDialog />
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  );
}
