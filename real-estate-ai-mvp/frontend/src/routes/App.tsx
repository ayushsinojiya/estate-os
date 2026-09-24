import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Loading, Empty } from "../components/ui";
import { AppLayout } from "../layouts/AppLayout";
import { Login } from "../pages/Login";
import { Dashboard } from "../pages/Dashboard";
import { Projects, ProjectDetail, Units, Documents } from "../pages/Projects";
import { Leads, LeadDetail } from "../pages/Leads";
import { Calls, CallDetail } from "../pages/Calls";
import { Recommendations } from "../pages/Recommendations";
import { SiteVisits, SiteVisitDetail } from "../pages/SiteVisits";
import { Handovers } from "../pages/Handovers";
import { Notifications, Profile, AuditLogs } from "../pages/Settings";
import { Files } from "../pages/Files";
export function ProtectedRoute() {
  const { session, loading } = useAuth();
  const location = useLocation();
  return loading ? (
    <Loading />
  ) : session ? (
    <Outlet />
  ) : (
    <Navigate
      to="/login"
      replace
      state={{ from: location.pathname + location.search }}
    />
  );
}
function ManagementRoute() {
  const { canManage } = useAuth();
  return canManage ? (
    <Outlet />
  ) : (
    <Empty
      title="Restricted workspace area"
      description="Your current role does not have access to the audit trail."
    />
  );
}
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="projects/:id/units" element={<Units />} />
          <Route path="projects/:id/documents" element={<Documents />} />
          <Route path="files" element={<Files />} />
          <Route path="leads" element={<Leads />} />
          <Route path="leads/:id" element={<LeadDetail />} />
          <Route path="calls" element={<Calls />} />
          <Route path="calls/:id" element={<CallDetail />} />
          <Route path="recommendations" element={<Recommendations />} />
          <Route path="site-visits" element={<SiteVisits />} />
          <Route path="site-visits/:id" element={<SiteVisitDetail />} />
          <Route path="handovers" element={<Handovers />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="settings/profile" element={<Profile />} />
          <Route element={<ManagementRoute />}>
            <Route path="audit-logs" element={<AuditLogs />} />
          </Route>
          <Route
            path="*"
            element={
              <Empty
                title="This page has moved"
                description="Use the workspace navigation to find your next step."
              />
            }
          />
        </Route>
      </Route>
    </Routes>
  );
}
