import { ContentLayout, Header, Container } from '@cloudscape-design/components';

export default function PlaceholderPage({ title, description }: { title: string, description: string }) {
  return (
    <ContentLayout
      header={
        <Header variant="h1" description={description}>
          {title}
        </Header>
      }
    >
      <Container>
        <h3>Under Construction</h3>
        <p>This module is currently being migrated to the new Cloudscape interface.</p>
      </Container>
    </ContentLayout>
  );
}
