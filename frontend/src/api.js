export const authFetch = async (url, options = {}) => {
  const token = localStorage.getItem('nim_auth_token');
  const headers = {
    ...(options.headers || {}),
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  };
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401 && !url.includes('/api/auth/status') && !url.includes('/api/auth/login')) {
    localStorage.removeItem('nim_auth_token');
    window.dispatchEvent(new CustomEvent('nim-auth-expired'));
  }
  return res;
};
