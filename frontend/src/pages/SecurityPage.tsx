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
  Flashbar,
  Table,
  Badge
} from '@cloudscape-design/components';

export default function SecurityPage() {
  const [apiKeys, setApiKeys] = useState<any>({});
  const [notifications, setNotifications] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api-keys').then(r => r.json()).then(setApiKeys).catch(console.error);
  }, []);

  const handleKeyChange = (key: string, value: any) => {
    setApiKeys({ ...apiKeys, [key]: value });
  };

  const saveApiKey = async (key: string) => {
    try {
      await fetch('/api-keys/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value: apiKeys[key] })
      });
      setNotifications([{ type: 'success', content: `API Key ${key} updated successfully`, dismissible: true, id: Date.now().toString() }]);
    } catch (err: any) {
      setNotifications([{ type: 'error', content: err.message, dismissible: true, id: Date.now().toString() }]);
    }
  };

  return (
    <ContentLayout header={<Header variant="h1" description="Manage access, credentials, and API connections">Security & API Keys</Header>}>
      <SpaceBetween size="l">
        {notifications.length > 0 && <Flashbar items={notifications} />}

        <Container header={<Header variant="h2">Third-Party API Keys</Header>}>
          <Form>
            <SpaceBetween direction="vertical" size="m">
              {Object.keys(apiKeys).map(k => (
                <FormField key={k} label={k}>
                  <SpaceBetween direction="horizontal" size="s">
                    <div style={{ width: '400px' }}>
                      <Input
                        value={apiKeys[k] || ''}
                        onChange={({ detail }) => handleKeyChange(k, detail.value)}
                        placeholder="••••••••••••••••"
                      />
                    </div>
                    <Button onClick={() => saveApiKey(k)}>Update</Button>
                  </SpaceBetween>
                </FormField>
              ))}
            </SpaceBetween>
          </Form>
        </Container>

        <Container header={<Header variant="h2">Change Password</Header>}>
          <Form
            actions={<Button variant="primary">Update Password</Button>}
          >
            <SpaceBetween direction="vertical" size="m">
              <FormField label="Current Password">
                <Input value="" onChange={() => {}} type="password" />
              </FormField>
              <FormField label="New Password">
                <Input value="" onChange={() => {}} type="password" />
              </FormField>
            </SpaceBetween>
          </Form>
        </Container>

        <Container header={<Header variant="h2">Active Sessions</Header>}>
          <Table
            items={[
              { id: '1', ip: '192.168.1.1', location: 'Local Network', lastActive: 'Just now', current: true },
              { id: '2', ip: '104.28.x.x', location: 'Seattle, WA', lastActive: '2 days ago', current: false }
            ]}
            columnDefinitions={[
              { id: 'ip', header: 'IP Address', cell: e => e.ip },
              { id: 'location', header: 'Location', cell: e => e.location },
              { id: 'lastActive', header: 'Last Active', cell: e => e.lastActive },
              { id: 'current', header: 'Status', cell: e => e.current ? <Badge color="green">Current Session</Badge> : <Button variant="inline-link">Revoke</Button> }
            ]}
          />
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
