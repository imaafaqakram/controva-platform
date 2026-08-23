
import SideNavigation from '@cloudscape-design/components/side-navigation';
import { useLocation, useNavigate } from 'react-router-dom';

export default function AppSideNavigation() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <SideNavigation
      activeHref={location.pathname}
      onFollow={event => {
        if (!event.detail.external) {
          event.preventDefault();
          navigate(event.detail.href);
        }
      }}
      header={{ href: '/', text: 'Controva Platform' }}
      items={[
        { type: 'link', text: 'Dashboard', href: '/' },
        {
          type: 'section',
          text: 'Lead Operations',
          items: [
            { type: 'link', text: 'Search & Discovery', href: '/search' },
            { type: 'link', text: 'Leads Database', href: '/leads' },
            { type: 'link', text: 'Pipeline', href: '/pipeline' },
            { type: 'link', text: 'Outreach', href: '/outreach' },
          ]
        },
        {
          type: 'section',
          text: 'Analytics & Intelligence',
          items: [
            { type: 'link', text: 'Analytics', href: '/analytics' },
            { type: 'link', text: 'SEO Research', href: '/seo' },
            { type: 'link', text: 'Competitor Intel', href: '/competitors' },
            { type: 'link', text: 'People Finder', href: '/people' },
            { type: 'link', text: 'Social Scout', href: '/social' },
            { type: 'link', text: 'E-commerce Research', href: '/ecommerce' },
          ]
        },
        { type: 'divider' },
        {
          type: 'section',
          text: 'System',
          items: [
            { type: 'link', text: 'Settings', href: '/settings' },
          ]
        }
      ]}
    />
  );
}
