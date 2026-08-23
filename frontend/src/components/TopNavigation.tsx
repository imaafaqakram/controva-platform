
import TopNavigation from '@cloudscape-design/components/top-navigation';
import { useNavigate } from 'react-router-dom';

export default function AppTopNavigation() {
  const navigate = useNavigate();
  return (
    <TopNavigation
      identity={{
        href: '/',
        title: 'Controva Intelligence Platform',
        onFollow: (e) => {
          e.preventDefault();
          navigate('/');
        }
      }}
      utilities={[
        {
          type: 'button',
          iconName: 'notification',
          title: 'Notifications',
          ariaLabel: 'Notifications (unread)',
          badge: true,
          disableUtilityCollapse: false
        },
        {
          type: 'menu-dropdown',
          text: 'Settings',
          description: 'admin@controvallc.com',
          iconName: 'user-profile',
          onItemClick: (e) => {
            if (e.detail.id === 'preferences') navigate('/preferences');
            if (e.detail.id === 'profile') navigate('/profile');
            if (e.detail.id === 'security') navigate('/security');
            if (e.detail.id === 'documentation') navigate('/docs');
            if (e.detail.id === 'support') navigate('/docs');
          },
          items: [
            { id: 'profile', text: 'Profile' },
            { id: 'preferences', text: 'Preferences' },
            { id: 'security', text: 'Security' },
            {
              id: 'support-group',
              text: 'Support',
              items: [
                { id: 'documentation', text: 'Documentation' },
                { id: 'support', text: 'Developer Guide' }
              ]
            },
            { id: 'signout', text: 'Sign out' }
          ]
        }
      ]}
      i18nStrings={{
        searchIconAriaLabel: 'Search',
        searchDismissIconAriaLabel: 'Close search',
        overflowMenuTriggerText: 'More',
        overflowMenuTitleText: 'All',
        overflowMenuBackIconAriaLabel: 'Back',
        overflowMenuDismissIconAriaLabel: 'Close menu'
      }}
    />
  );
}
