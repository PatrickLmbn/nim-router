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

// Google's own sign-in endpoints accept these to change the account picker
// behaviour WITHOUT terminating the browser's Google session.
//
// 'accounts.google.com/Logout' must NOT be used here: it signs the user out of
// Google entirely (every account in the browser), not just the account we are
// swapping away from. That was the old behaviour and it logged the user out of
// Gmail, Drive and every other Google app in the same browser.
const GOOGLE_ACCOUNT_CHOOSER = 'https://accounts.google.com/AccountChooser';
const GOOGLE_SIGNIN_HOSTS = ['accounts.google.com', 'accounts.google.co.uk', 'accounts.google.de'];

// Ask Google to show the account picker rather than silently reusing the
// session's last account. 'select_account' always shows the picker;
// 'select_account add_account' also offers the "Use another account" button.
const ACCOUNT_CHOOSER_PROMPT = 'select_account';

// Google rejects unknown parameters on some endpoints, so only the ones we
// know it honours are forwarded.
const GOOGLE_PROMPT_PARAMS = ['prompt'];

/**
 * Fetch an OAuth authorization URL server-side and rewrite it so Google shows
 * the account picker.
 *
 * Some providers (Kiro) route sign-in through AWS Cognito, which builds the
 * Google authorization URL itself and does NOT forward any hint we add to the
 * URL we hand it. For those we resolve the redirect chain here, take the final
 * Google URL, and add the account-picker hint to it.
 *
 * @param {string} authUrl        Authorization URL returned by the backend.
 * @param {boolean} forceChooser  Always show the account picker.
 * @returns {Promise<string>}     The URL to open in the sign-in popup.
 */
const withAccountChooser = async (authUrl, forceChooser) => {
  if (!forceChooser) return authUrl;

  let target = authUrl;
  const host = (() => {
    try { return new URL(authUrl).hostname; } catch (e) { return ''; }
  })();

  // Direct Google OAuth URL: add the hint ourselves.
  if (GOOGLE_SIGNIN_HOSTS.includes(host)) {
    return appendGoogleParams(authUrl, { prompt: ACCOUNT_CHOOSER_PROMPT });
  }

  // Indirect (e.g. AWS Cognito): resolve the chain to the real Google URL.
  try {
    const res = await fetch(authUrl, { method: 'GET', redirect: 'manual' });
    const location = res.headers.get('location');
    if (location) {
      let next = new URL(location, authUrl).toString();
      // Cognito redirects to Google; follow one more hop if it bounces.
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
    // Network hiccup: fall through and open the URL unchanged.
  }

  return target;
};

/**
 * Add query parameters to a URL, preserving any that already exist.
 */
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

/**
 * Drive an OAuth popup through sign-in.
 *
 * @param {Window}   win      The popup window to drive.
 * @param {string}   authUrl  Authorization URL from the backend.
 * @param {string}   label    Provider name, used in error messages.
 * @param {boolean}  forceChooser  Show Google's account picker.
 */
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

  // Resolve the final URL (and add the account chooser hint) before navigating.
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
