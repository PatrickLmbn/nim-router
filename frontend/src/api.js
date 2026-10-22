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

const GOOGLE_ACCOUNT_CHOOSER = 'https://accounts.google.com/AccountChooser';
const GOOGLE_SIGNIN_HOSTS = ['accounts.google.com', 'accounts.google.co.uk', 'accounts.google.de'];

const ACCOUNT_CHOOSER_PROMPT = 'select_account';

const GOOGLE_PROMPT_PARAMS = ['prompt'];

const withAccountChooser = async (authUrl, forceChooser) => {
  if (!forceChooser) return authUrl;

  let target = authUrl;
  const host = (() => {
    try { return new URL(authUrl).hostname; } catch (e) { return ''; }
  })();

  if (GOOGLE_SIGNIN_HOSTS.includes(host)) {
    return appendGoogleParams(authUrl, { prompt: ACCOUNT_CHOOSER_PROMPT });
  }

  try {
    const res = await fetch(authUrl, { method: 'GET', redirect: 'manual' });
    const location = res.headers.get('location');
    if (location) {
      let next = new URL(location, authUrl).toString();
      let hops = 0;
      while (hops < 3) {
        const nextHost = (() => {
          try { return new URL(next).hostname; } catch (e) { return ''; }
        })();
        if (GOOGLE_SIGNIN_HOSTS.includes(nextHost)) {
          return appendGoogleParams(next, { prompt: ACCOUNT_CHOOSER_PROMPT });
        }
        const hop = await fetch(next, { method: 'GET', redirect: 'manual' });
        const hopLoc = hop.headers.get('location');
        if (!hopLoc) break;
        next = new URL(hopLoc, next).toString();
        hops += 1;
      }
      target = next;
    }
  } catch (e) {
  }

  return target;
};

const appendGoogleParams = (url, params) => {
  try {
    const parsed = new URL(url);
    GOOGLE_PROMPT_PARAMS.forEach((key) => {
      if (params[key] !== undefined) parsed.searchParams.set(key, params[key]);
    });
    return parsed.toString();
  } catch (e) {
    return url;
  }
};

const startOAuthFlow = (win, authUrl, label, forceChooser = false) => new Promise((resolve) => {
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

  const navigateToAuth = () => {
    try {
      win.location.replace(authUrl);
      finish({ ok: true });
    } catch (e) {
      finish({ ok: false, error: `Could not open the ${label} sign-in window.` });
    }
  };

  withAccountChooser(authUrl, forceChooser).then((finalUrl) => {
    try {
      win.location.replace(finalUrl);
      finish({ ok: true });
    } catch (e) {
      finish({ ok: false, error: `Could not open the ${label} sign-in window.` });
    }
  }).catch(() => {
    navigateToAuth();
  });
});

export const openKiroOAuthWindow = () => {
  try {
    return window.open('about:blank', 'kiro_oauth', 'width=560,height=780');
  } catch (e) {
    return null;
  }
};

export const startKiroOAuthFlow = (win, authUrl, forceChooser = false) =>
  startOAuthFlow(win, authUrl, 'Kiro', forceChooser);

export const openAntigravityOAuthWindow = () => {
  try {
    return window.open('about:blank', 'antigravity_oauth', 'width=560,height=780');
  } catch (e) {
    return null;
  }
};

export const startAntigravityOAuthFlow = (win, authUrl, forceChooser = false) =>
  startOAuthFlow(win, authUrl, 'Antigravity', forceChooser);

export { GOOGLE_ACCOUNT_CHOOSER, ACCOUNT_CHOOSER_PROMPT };
