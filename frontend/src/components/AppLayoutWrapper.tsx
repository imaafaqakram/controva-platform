import { useState } from 'react';
import AppLayout from '@cloudscape-design/components/app-layout';
import AppSideNavigation from './SideNavigation';
import { Outlet, useLocation } from 'react-router-dom';

export default function AppLayoutWrapper() {
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);
  const location = useLocation();

  // Optionally hide navigation/tools on specific routes
  const isDashboard = location.pathname === '/';

  return (
    <AppLayout
      navigation={<AppSideNavigation />}
      navigationOpen={navigationOpen}
      onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
      toolsOpen={toolsOpen}
      onToolsChange={({ detail }) => setToolsOpen(detail.open)}
      content={<Outlet />}
      contentType={isDashboard ? 'dashboard' : 'default'}
      toolsHide={true} // Hide right panel for now until we add Lead Details Drawer
    />
  );
}
