import { useEffect, useState } from 'react';
import {
  ContentLayout,
  Header,
  Container,
  SpaceBetween,
  Button,
  Grid,
  Box,
  BarChart,
  PieChart
} from '@cloudscape-design/components';

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [charts, setCharts] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/stats').then(r => r.json()),
      fetch('/stats-chart').then(r => r.json())
    ])
      .then(([statsData, chartData]) => {
        setStats(statsData);
        setCharts(chartData);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching dashboard data:', err);
        setLoading(false);
      });
  }, []);

  return (
    <ContentLayout
      header={
        <SpaceBetween size="m">
          <Header
            variant="h1"
            actions={<Button variant="primary">Start New Search</Button>}
            description="Overview of your lead generation pipeline"
          >
            Dashboard
          </Header>
        </SpaceBetween>
      }
    >
      <SpaceBetween size="l">
        <Grid gridDefinition={[{ colspan: 3 }, { colspan: 3 }, { colspan: 3 }, { colspan: 3 }]}>
          <Container>
            <Box variant="awsui-key-label">Total Leads</Box>
            <Box variant="awsui-value-large">{loading ? '...' : stats?.total || 0}</Box>
          </Container>
          <Container>
            <Box variant="awsui-key-label">Hot Leads</Box>
            <Box variant="awsui-value-large">{loading ? '...' : stats?.hot_leads || 0}</Box>
          </Container>
          <Container>
            <Box variant="awsui-key-label">With Email</Box>
            <Box variant="awsui-value-large">{loading ? '...' : stats?.with_email || 0}</Box>
          </Container>
          <Container>
            <Box variant="awsui-key-label">High AI Score</Box>
            <Box variant="awsui-value-large">{loading ? '...' : stats?.high_score || 0}</Box>
          </Container>
        </Grid>

        <Grid gridDefinition={[{ colspan: 8 }, { colspan: 4 }]}>
          <Container header={<Header variant="h2">Leads by Status</Header>}>
            <BarChart
              series={[
                {
                  title: 'Leads',
                  type: 'bar',
                  data: charts?.status_breakdown?.map((s: any) => ({
                    x: s.status,
                    y: s.count
                  })) || []
                }
              ]}
              xDomain={charts?.status_breakdown?.map((s: any) => s.status) || []}
              yDomain={[0, Math.max(...(charts?.status_breakdown?.map((s: any) => s.count) || [10])) + 5]}
              i18nStrings={{
                filterLabel: 'Filter displayed data',
                filterPlaceholder: 'Filter data',
                filterSelectedAriaLabel: 'selected',
                legendAriaLabel: 'Legend',
                chartAriaRoleDescription: 'bar chart',
                xTickFormatter: e => e?.toString() || '',
                yTickFormatter: e => e?.toString() || ''
              }}
              ariaLabel="Leads by Status"
              height={300}
              statusType={loading ? 'loading' : 'finished'}
            />
          </Container>

          <Container header={<Header variant="h2">AI Score Distribution</Header>}>
            <PieChart
              data={charts?.score_distribution?.map((s: any) => ({
                title: s.bucket,
                value: s.count
              })) || []}
              i18nStrings={{
                detailsValue: 'Value',
                detailsPercentage: 'Percentage',
                filterLabel: 'Filter displayed data',
                filterPlaceholder: 'Filter data',
                filterSelectedAriaLabel: 'selected',
                legendAriaLabel: 'Legend',
                chartAriaRoleDescription: 'pie chart',
                segmentAriaRoleDescription: 'segment'
              }}
              ariaLabel="Score Distribution"
              size="medium"
              statusType={loading ? 'loading' : 'finished'}
            />
          </Container>
        </Grid>
      </SpaceBetween>
    </ContentLayout>
  );
}
