import { useEffect, useState } from 'react';
import {
  ContentLayout,
  Header,
  SpaceBetween,
  Container,
  Badge
} from '@cloudscape-design/components';

const PIPELINE_STAGES = [
  { id: 'discovered', title: 'Discovered', color: 'grey' },
  { id: 'enriched', title: 'Enriched', color: 'blue' },
  { id: 'scored', title: 'Scored', color: 'purple' },
  { id: 'ready', title: 'Ready', color: 'green' },
  { id: 'sent', title: 'Sent', color: 'red' },
];

export default function PipelinePage() {
  const [leads, setLeads] = useState<any[]>([]);

  useEffect(() => {
    fetch('/leads')
      .then(r => r.json())
      .then(data => {
        setLeads(data.leads || []);
      })
      .catch(err => {
        console.error('Error fetching leads:', err);
      });
  }, []);

  const getLeadsByStatus = (status: string) => leads.filter(l => l.status === status);

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Visual pipeline of your lead workflow">
          Pipeline
        </Header>
      }
    >
      <div style={{ overflowX: 'auto', paddingBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '20px', minWidth: '1200px' }}>
          {PIPELINE_STAGES.map(stage => {
            const stageLeads = getLeadsByStatus(stage.id);
            return (
              <div key={stage.id} style={{ flex: 1, minWidth: '280px' }}>
                <Container
                  header={
                    <SpaceBetween direction="horizontal" size="s" alignItems="center">
                      <Header variant="h2">{stage.title}</Header>
                      <Badge color={stage.color as any}>{stageLeads.length}</Badge>
                    </SpaceBetween>
                  }
                  fitHeight={true}
                >
                  <SpaceBetween size="m">
                    {stageLeads.map(lead => (
                      <Container key={lead.id} disableContentPaddings={false}>
                        <SpaceBetween size="xs">
                          <div style={{ fontWeight: 'bold' }}>{lead.business_name}</div>
                          <div style={{ fontSize: '12px', color: '#555' }}>{lead.city}</div>
                          {lead.ai_score && (
                            <Badge color={lead.ai_score >= 7 ? 'green' : 'grey'}>
                              Score: {lead.ai_score}
                            </Badge>
                          )}
                        </SpaceBetween>
                      </Container>
                    ))}
                    {stageLeads.length === 0 && (
                      <div style={{ textAlign: 'center', color: '#666', padding: '20px' }}>
                        No leads in this stage
                      </div>
                    )}
                  </SpaceBetween>
                </Container>
              </div>
            );
          })}
        </div>
      </div>
    </ContentLayout>
  );
}
