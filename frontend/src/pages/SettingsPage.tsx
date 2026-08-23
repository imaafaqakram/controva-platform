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
  Toggle
} from '@cloudscape-design/components';

export default function SettingsPage() {
  const [config, setConfig] = useState<any>({});
  const [apiKeys, setApiKeys] = useState<any>({});
  const [notifications, setNotifications] = useState<any[]>([]);

  useEffect(() => {
    fetch('/config').then(r => r.json()).then(setConfig).catch(console.error);
    fetch('/api-keys').then(r => r.json()).then(setApiKeys).catch(console.error);
  }, []);

  const handleConfigChange = (key: string, value: any) => {
    setConfig({ ...config, [key]: value });
  };

  const handleKeyChange = (key: string, value: any) => {
    setApiKeys({ ...apiKeys, [key]: value });
  };

  const saveConfig = async () => {
    try {
      await fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      setNotifications([{ type: 'success', content: 'Settings saved successfully', dismissible: true, id: Date.now().toString() }]);
    } catch (err: any) {
      setNotifications([{ type: 'error', content: err.message, dismissible: true, id: Date.now().toString() }]);
    }
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
    <ContentLayout header={<Header variant="h1">Settings</Header>}>
      <SpaceBetween size="l">
        {notifications.length > 0 && <Flashbar items={notifications} />}

        <Container
          header={
            <Header variant="h2" actions={<Button variant="primary" onClick={saveConfig}>Save System Settings</Button>}>
              System Configuration
            </Header>
          }
        >
          <Form>
            <SpaceBetween direction="vertical" size="m">
              <FormField label="Target Location (Default)">
                <Input value={config.target_location || ''} onChange={({ detail }) => handleConfigChange('target_location', detail.value)} />
              </FormField>
              <FormField label="Default Niche">
                <Input value={config.default_niche || ''} onChange={({ detail }) => handleConfigChange('default_niche', detail.value)} />
              </FormField>
              <FormField>
                <Toggle checked={config.auto_email_copy || false} onChange={({ detail }) => handleConfigChange('auto_email_copy', detail.checked)}>
                  Auto-generate email copy
                </Toggle>
              </FormField>
              <FormField>
                <Toggle checked={config.auto_enrich || false} onChange={({ detail }) => handleConfigChange('auto_enrich', detail.checked)}>
                  Auto-enrich leads
                </Toggle>
              </FormField>
            </SpaceBetween>
          </Form>
        </Container>

        <Container header={<Header variant="h2">API Keys</Header>}>
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
      </SpaceBetween>
    </ContentLayout>
  );
}
