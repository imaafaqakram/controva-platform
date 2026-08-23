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

export default function PreferencesPage() {
  const [config, setConfig] = useState<any>({});
  const [notifications, setNotifications] = useState<any[]>([]);

  useEffect(() => {
    fetch('/config').then(r => r.json()).then(setConfig).catch(console.error);
  }, []);

  const handleConfigChange = (key: string, value: any) => {
    setConfig({ ...config, [key]: value });
  };

  const saveConfig = async () => {
    try {
      await fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      setNotifications([{ type: 'success', content: 'Preferences saved successfully', dismissible: true, id: Date.now().toString() }]);
    } catch (err: any) {
      setNotifications([{ type: 'error', content: err.message, dismissible: true, id: Date.now().toString() }]);
    }
  };

  return (
    <ContentLayout header={<Header variant="h1" description="Configure system-wide lead generation preferences">Preferences</Header>}>
      <SpaceBetween size="l">
        {notifications.length > 0 && <Flashbar items={notifications} />}

        <Container
          header={
            <Header variant="h2" actions={<Button variant="primary" onClick={saveConfig}>Save Preferences</Button>}>
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
      </SpaceBetween>
    </ContentLayout>
  );
}
