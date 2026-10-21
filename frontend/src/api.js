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

const GOOGLE_LOGOUT_URL = 'https://accounts.google.com/Logout';
const GOOGLE_COOKIE_CLEAR_DELAY_MS = 600;

export const openKiroOAuthWindow = () => {
  try {
    return window.open('about:blank', 'kiro_oauth', 'width=560,height=780');
  } catch (e) {
    return null;
  }
};

export const startKiroOAuthFlow = (win, authUrl) => new Promise((resolve) => {
  let settled = false;
  const finish = (result) => {
    if (settled) return;
    settled = true;
    resolve(result);
  };

  if (!win || win.closed) {
    finish({ ok: false, error: 'Popup blocked. Allow popups for this site and try again.' });
    return;
  }

  let loaded = false;
  try {
    win.addEventListener('load', () => { loaded = true; });
  } catch (e) {
  }

  const navigateToAuth = () => {
    try {
      win.location.replace(authUrl);
      finish({ ok: true });
    } catch (e) {
      finish({ ok: false, error: 'Could not open the Kiro sign-in window.' });
    }
  };

  try {
    win.location.replace(GOOGLE_LOGOUT_URL);
  } catch (e) {
    finish({ ok: false, error: 'Could not open the Kiro sign-in window.' });
    return;
  }

  const started = Date.now();
  const poll = setInterval(() => {
    const elapsed = Date.now() - started;
    if ((loaded && elapsed > GOOGLE_COOKIE_CLEAR_DELAY_MS) || elapsed > 8000) {
      clearInterval(poll);
      navigateToAuth();
    }
  }, 100);
});