export const ROLE_ORDER = {
  viewer: 1,
  operator: 2,
  admin: 3,
};

export const normalizeRole = (role) => {
  if (!role) return 'viewer';
  if (role.startsWith('org:')) return role.replace('org:', '');
  return role;
};

export const hasMinRole = (role, minRole) => {
  const normalized = normalizeRole(role);
  const min = normalizeRole(minRole);
  return (ROLE_ORDER[normalized] || 0) >= (ROLE_ORDER[min] || 0);
};
