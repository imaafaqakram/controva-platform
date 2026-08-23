
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import '@cloudscape-design/global-styles/index.css';
import AppTopNavigation from './components/TopNavigation';
import AppLayoutWrapper from './components/AppLayoutWrapper';
import DashboardPage from './pages/DashboardPage';
import LeadsPage from './pages/LeadsPage';
import SearchPage from './pages/SearchPage';
import PipelinePage from './pages/PipelinePage';
import ProfilePage from './pages/ProfilePage';
import PreferencesPage from './pages/PreferencesPage';
import SecurityPage from './pages/SecurityPage';
import DocumentationPage from './pages/DocumentationPage';
import PlaceholderPage from './pages/PlaceholderPage';

function App() {
  return (
    <BrowserRouter>
      <div id="h" style={{ position: 'sticky', top: 0, zIndex: 1002 }}>
        <AppTopNavigation />
      </div>
      <Routes>
        <Route element={<AppLayoutWrapper />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/leads" element={<LeadsPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/settings" element={<PreferencesPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/preferences" element={<PreferencesPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/outreach" element={<PlaceholderPage title="Outreach" description="Manage email outreach campaigns." />} />
          <Route path="/analytics" element={<PlaceholderPage title="Analytics" description="Advanced insights and reporting." />} />
          <Route path="/seo" element={<PlaceholderPage title="SEO Research" description="Perform keyword and SERP analysis." />} />
          <Route path="/competitors" element={<PlaceholderPage title="Competitor Intel" description="Analyze competitors." />} />
          <Route path="/people" element={<PlaceholderPage title="People Finder" description="Find contacts for specific domains." />} />
          <Route path="/social" element={<PlaceholderPage title="Social Scout" description="Scout social media profiles." />} />
          <Route path="/ecommerce" element={<PlaceholderPage title="E-commerce Research" description="Analyze e-commerce niches." />} />
          <Route path="*" element={<DashboardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
