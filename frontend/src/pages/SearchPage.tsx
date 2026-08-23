import { useState, useEffect } from 'react';
import {
  ContentLayout,
  Header,
  SpaceBetween,
  Button,
  Container,
  Form,
  FormField,
  Input,
  Select,
  Checkbox,
  Flashbar,
  Table,
  Badge
} from '@cloudscape-design/components';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [filterMode, setFilterMode] = useState({ label: 'No Website Only (Lead Gen)', value: 'no_website' });
  const [density, setDensity] = useState({ label: 'Standard', value: 'standard' });
  const [findMore, setFindMore] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);

  useEffect(() => {
    fetchBatches();
    const interval = setInterval(fetchBatches, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchBatches = async () => {
    try {
      const res = await fetch('/batches');
      const data = await res.json();
      setBatches(data.batches || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query) return;

    setIsSubmitting(true);
    try {
      const res = await fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          filter_mode: filterMode.value,
          density: density.value,
          find_more: findMore
        })
      });
      const data = await res.json();

      if (data.error) {
        setNotifications([{ type: 'error', content: data.error, dismissible: true, id: Date.now().toString() }]);
      } else {
        setNotifications([
          { type: 'success', content: `Search started successfully! Job ID: ${data.job_id}`, dismissible: true, id: Date.now().toString() }
        ]);
        setQuery('');
        fetchBatches();
      }
    } catch (err: any) {
      setNotifications([{ type: 'error', content: err.message, dismissible: true, id: Date.now().toString() }]);
    }
    setIsSubmitting(false);
  };

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Discover new leads using natural language search">
          Search & Discovery
        </Header>
      }
    >
      <SpaceBetween size="l">
        {notifications.length > 0 && <Flashbar items={notifications} />}

        <form onSubmit={handleSubmit}>
          <Form
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button formAction="none" variant="link" onClick={() => setQuery('')}>
                  Cancel
                </Button>
                <Button variant="primary" loading={isSubmitting}>
                  Start Discovery
                </Button>
              </SpaceBetween>
            }
          >
            <Container header={<Header variant="h2">New Search</Header>}>
              <SpaceBetween direction="vertical" size="l">
                <FormField
                  label="Search Query"
                  description="E.g., 'plumbers in Seattle' or 'dentists in London UK'"
                >
                  <Input
                    value={query}
                    onChange={({ detail }) => setQuery(detail.value)}
                    placeholder="Enter business type and location..."
                  />
                </FormField>

                <FormField label="Filter Mode">
                  <Select
                    selectedOption={filterMode}
                    onChange={({ detail }) => setFilterMode(detail.selectedOption as any)}
                    options={[
                      { label: 'No Website Only (Lead Gen)', value: 'no_website' },
                      { label: 'With Website Only (SEO/Audit)', value: 'with_website' },
                      { label: 'All Businesses', value: 'all' }
                    ]}
                  />
                </FormField>

                <FormField label="Search Density" description="Higher density takes longer but finds more results.">
                  <Select
                    selectedOption={density}
                    onChange={({ detail }) => setDensity(detail.selectedOption as any)}
                    options={[
                      { label: 'Low (Fastest)', value: 'low' },
                      { label: 'Standard (Recommended)', value: 'standard' },
                      { label: 'High (Thorough)', value: 'high' }
                    ]}
                  />
                </FormField>

                <FormField>
                  <Checkbox
                    checked={findMore}
                    onChange={({ detail }) => setFindMore(detail.checked)}
                  >
                    Enable "Find More" (Deep grid search for large cities)
                  </Checkbox>
                </FormField>
              </SpaceBetween>
            </Container>
          </Form>
        </form>

        <Container header={<Header variant="h2">Running Batches</Header>}>
          <Table
            items={batches}
            columnDefinitions={[
              { id: 'id', header: 'Job ID', cell: e => e.id },
              { id: 'status', header: 'Status', cell: e => <Badge color={e.status === 'running' ? 'blue' : 'grey'}>{e.status}</Badge> },
              { id: 'step', header: 'Step', cell: e => e.step || '-' },
              { id: 'progress', header: 'Progress', cell: e => `${e.progress || 0}%` },
            ]}
            empty={
              <div style={{ textAlign: 'center' }}>
                <p>No active searches.</p>
              </div>
            }
          />
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
