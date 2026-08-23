import { useEffect, useState } from 'react';
import {
  ContentLayout,
  Header,
  SpaceBetween,
  Button,
  Table,
  Pagination,
  TextFilter,
  Badge,
  Link
} from '@cloudscape-design/components';
import { useCollection } from '@cloudscape-design/collection-hooks';

export default function LeadsPage() {
  const [leads, setLeads] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/leads')
      .then(r => r.json())
      .then(data => {
        setLeads(data.leads || []);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching leads:', err);
        setLoading(false);
      });
  }, []);

  const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(
    leads,
    {
      filtering: {
        empty: (
          <div style={{ textAlign: 'center' }}>
            <b>No leads found</b>
            <p>No leads match the current filters.</p>
          </div>
        ),
        noMatch: (
          <div style={{ textAlign: 'center' }}>
            <b>No matches</b>
            <p>We can't find a match.</p>
            <Button onClick={() => actions.setFiltering('')}>Clear filter</Button>
          </div>
        )
      },
      pagination: { pageSize: 20 },
      sorting: { defaultState: { sortingColumn: { sortingField: 'created_at' }, isDescending: true } }
    }
  );

  return (
    <ContentLayout
      header={
        <SpaceBetween size="m">
          <Header
            variant="h1"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button iconName="download">Export CSV</Button>
                <Button variant="primary">New Search</Button>
              </SpaceBetween>
            }
            description="Manage and track your discovered leads"
          >
            Leads Database
          </Header>
        </SpaceBetween>
      }
    >
      <Table
        {...collectionProps}
        items={items}
        loading={loading}
        loadingText="Loading leads..."
        columnDefinitions={[
          {
            id: 'business_name',
            header: 'Business Name',
            cell: e => <Link href={`/lead/${e.id}`}>{e.business_name}</Link>,
            sortingField: 'business_name',
            isRowHeader: true
          },
          {
            id: 'niche',
            header: 'Niche',
            cell: e => e.niche,
            sortingField: 'niche'
          },
          {
            id: 'location',
            header: 'Location',
            cell: e => `${e.city || ''} ${e.country || ''}`.trim(),
            sortingField: 'city'
          },
          {
            id: 'email',
            header: 'Contact',
            cell: e => e.email || '-',
            sortingField: 'email'
          },
          {
            id: 'ai_score',
            header: 'AI Score',
            cell: e => {
              if (!e.ai_score) return '-';
              return <Badge color={e.ai_score >= 7 ? 'green' : e.ai_score >= 5 ? 'blue' : 'grey'}>{e.ai_score}/10</Badge>;
            },
            sortingField: 'ai_score'
          },
          {
            id: 'status',
            header: 'Status',
            cell: e => <Badge>{e.status}</Badge>,
            sortingField: 'status'
          }
        ]}
        filter={
          <TextFilter
            {...filterProps}
            filteringPlaceholder="Search leads..."
            countText={`${filteredItemsCount} matches`}
          />
        }
        pagination={<Pagination {...paginationProps} />}
        empty={
          <div style={{ textAlign: 'center' }}>
            <b>No leads</b>
            <p>You don't have any leads yet.</p>
            <Button variant="primary">Start Search</Button>
          </div>
        }
      />
    </ContentLayout>
  );
}
