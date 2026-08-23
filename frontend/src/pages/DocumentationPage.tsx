import {
  ContentLayout,
  Header,
  SpaceBetween,
  Container,
  Tabs,
  Box
} from '@cloudscape-design/components';

export default function DocumentationPage() {
  return (
    <ContentLayout header={<Header variant="h1" description="Controva LeadGen Platform Documentation">Documentation Center</Header>}>
      <SpaceBetween size="l">
        <Container>
          <Tabs
            tabs={[
              {
                id: 'user-guide',
                label: 'User Guide',
                content: (
                  <SpaceBetween size="m">
                    <Header variant="h2">Getting Started</Header>
                    <Box variant="p">
                      Welcome to the Controva Intelligence Platform. This AWS-styled dashboard is your central command center for generating, enriching, and executing automated email campaigns for B2B leads.
                    </Box>

                    <Header variant="h3">1. Search & Discovery</Header>
                    <Box variant="p">
                      Navigate to the <b>Search & Discovery</b> tab to initiate a natural language search. The system uses advanced AI queries to scrape Google Maps and SERP data to discover raw leads based on your niche and location.
                    </Box>

                    <Header variant="h3">2. Leads Database</Header>
                    <Box variant="p">
                      The <b>Leads Database</b> stores every lead discovered. Here you can filter, sort, and export leads to CSV. Leads undergo automated background enrichment via Serper and Oxylabs to find emails and LinkedIn profiles.
                    </Box>

                    <Header variant="h3">3. Pipeline</Header>
                    <Box variant="p">
                      The <b>Pipeline</b> provides a Kanban-style visual overview of your leads' lifecycle: Discovered → Enriched → Scored → Ready → Sent.
                    </Box>
                  </SpaceBetween>
                )
              },
              {
                id: 'developer-guide',
                label: 'Developer Guide',
                content: (
                  <SpaceBetween size="m">
                    <Header variant="h2">Architecture Overview</Header>
                    <Box variant="p">
                      The platform is a decoupled modern application consisting of a Python Threading Server (Backend) and a React+Vite SPA (Frontend).
                    </Box>

                    <Header variant="h3">Backend Engine (Python)</Header>
                    <Box variant="p">
                      Located in <code>server/leads_api.py</code>, the backend runs on port <code>8080</code>. It uses Python's built-in <code>http.server</code> wrapped in a <code>ThreadingServer</code> to handle multiple requests. Background jobs (scraping, AI scoring) are dispatched as Daemon threads to prevent blocking the main HTTP listener.
                    </Box>

                    <Header variant="h3">Frontend UI (React/Vite)</Header>
                    <Box variant="p">
                      Located in <code>frontend/</code>, the UI is built using the official <b>AWS Cloudscape Design System</b>. During local development, the Vite dev server runs on port <code>5173</code> and proxies all <code>/api</code> or root data requests to <code>localhost:8080</code>.
                    </Box>

                    <Header variant="h3">How to Contribute (For New Developers)</Header>
                    <ul style={{ paddingLeft: '20px', lineHeight: '1.6' }}>
                      <li><b>Adding a new API endpoint:</b> Modify the <code>do_GET</code> or <code>do_POST</code> methods in <code>leads_api.py</code>. Return data using <code>self.send_json(200, data)</code>.</li>
                      <li><b>Adding a new UI Page:</b> Create a new component in <code>frontend/src/pages/</code> using Cloudscape components (<code>Container</code>, <code>SpaceBetween</code>, etc.). Register the route in <code>App.tsx</code>. Add a link to <code>SideNavigation.tsx</code>.</li>
                      <li><b>Running Locally:</b> Start backend with <code>python server/leads_api.py</code>. Start frontend with <code>cd frontend && npm run dev</code>.</li>
                      <li><b>Building for Production:</b> Run <code>npm run build</code> in the frontend directory. The resulting <code>dist</code> folder is automatically served by the Python backend when deployed.</li>
                    </ul>
                  </SpaceBetween>
                )
              }
            ]}
          />
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
