import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { EmptyState } from "./components/ui";
import AlertsPage from "./pages/AlertsPage";
import ChecklistPage from "./pages/ChecklistPage";
import ComparePage from "./pages/ComparePage";
import DashboardPage from "./pages/DashboardPage";
import DocumentsPage from "./pages/DocumentsPage";
import ImpactPage from "./pages/ImpactPage";
import RulesPage from "./pages/RulesPage";
import SearchPage from "./pages/SearchPage";
import SourceViewerPage from "./pages/SourceViewerPage";
import SystemPage from "./pages/SystemPage";
import WhatsNewPage from "./pages/WhatsNewPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="whats-new" element={<WhatsNewPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="viewer/:versionId" element={<SourceViewerPage />} />
        <Route path="impact" element={<ImpactPage />} />
        <Route path="checklist" element={<ChecklistPage />} />
        <Route path="rules" element={<RulesPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="*" element={<EmptyState title="Page not found">The address does not match any page in Reg IRIS.</EmptyState>} />
      </Route>
    </Routes>
  );
}
