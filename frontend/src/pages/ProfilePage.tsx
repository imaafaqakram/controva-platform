import {
  ContentLayout,
  Header,
  SpaceBetween,
  Container,
  Form,
  FormField,
  Input,
  Button,
  ColumnLayout,
  Box
} from '@cloudscape-design/components';
import { useState } from 'react';

export default function ProfilePage() {
  const [name, setName] = useState('Admin User');
  const [email, setEmail] = useState('admin@controvallc.com');
  const [company, setCompany] = useState('Controva LLC');

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Manage your personal account details">
          My Profile
        </Header>
      }
    >
      <SpaceBetween size="l">
        <Container header={<Header variant="h2">Account Information</Header>}>
          <Form
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button formAction="none" variant="link">
                  Cancel
                </Button>
                <Button variant="primary">Save Changes</Button>
              </SpaceBetween>
            }
          >
            <ColumnLayout columns={2}>
              <SpaceBetween direction="vertical" size="m">
                <FormField label="Full Name">
                  <Input value={name} onChange={e => setName(e.detail.value)} />
                </FormField>
                <FormField label="Email Address">
                  <Input value={email} onChange={e => setEmail(e.detail.value)} type="email" />
                </FormField>
                <FormField label="Company Name">
                  <Input value={company} onChange={e => setCompany(e.detail.value)} />
                </FormField>
              </SpaceBetween>

              <SpaceBetween direction="vertical" size="m">
                <FormField label="Role">
                  <Box variant="awsui-key-label">Administrator</Box>
                </FormField>
                <FormField label="Account Created">
                  <Box variant="awsui-key-label">August 14, 2026</Box>
                </FormField>
                <FormField label="Status">
                  <Box variant="awsui-key-label" color="text-status-success">Active</Box>
                </FormField>
              </SpaceBetween>
            </ColumnLayout>
          </Form>
        </Container>

        <Container header={<Header variant="h2">Danger Zone</Header>}>
          <SpaceBetween direction="vertical" size="s">
            <Box variant="p">Permanently delete your account and all associated data.</Box>
            <Button>Delete Account</Button>
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
