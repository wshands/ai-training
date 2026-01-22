let tokenGetter = null;

export const setTokenGetter = (getter) => {
  tokenGetter = getter;
};

export const getAuthToken = async () => {
  if (typeof tokenGetter === 'function') {
    return tokenGetter();
  }
  return null;
};
