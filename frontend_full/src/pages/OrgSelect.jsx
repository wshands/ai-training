import React from 'react';
import { OrganizationList } from '@clerk/clerk-react';

const OrgSelect = () => (
  <div className="max-w-md mx-auto">
    <h1 className="text-xl font-semibold mb-4">Choose organization</h1>
    <OrganizationList
      hidePersonal={false}
      afterSelectOrganizationUrl="/"
      afterCreateOrganizationUrl="/"
    />
  </div>
);

export default OrgSelect;
