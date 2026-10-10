import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ComparePage } from "@/features/compare/ComparePage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { DocumentDetailPage } from "@/features/documents/DocumentDetailPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { ImpactPage } from "@/features/impact/ImpactPage";
import { RunPage } from "@/features/impact/RunPage";
import { SearchPage } from "@/features/search/SearchPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="documents/:documentId" element={<DocumentDetailPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="impact" element={<ImpactPage />} />
          <Route path="impact/runs/:runId" element={<RunPage />} />
          <Route path="*" element={<div className="text-sm text-ink-soft">Page not found.</div>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
