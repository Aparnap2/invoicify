/**
 * Google OAuth2 Token Manager
 *
 * Handles OAuth2 flow for Google APIs including:
 * - Generating authorization URLs
 * - Exchanging authorization codes for tokens
 * - Refreshing access tokens
 * - Token storage and retrieval
 *
 * Run tests with: pnpm test -- test/lib/google/oauth.test.ts
 */

import type {
  GoogleOAuthConfig,
  GoogleOAuthToken,
  StoredGoogleCredentials,
  OAuthFlowResponse,
  TokenResponse,
} from './types.js';

// Default scopes for Sheets API
const DEFAULT_SCOPES = [
  'https://www.googleapis.com/auth/spreadsheets',
  'https://www.googleapis.com/auth/drive.readonly',
];

/**
 * Generate a cryptographically secure random string
 */
function generateState(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/**
 * Google OAuth2 Token Manager
 */
export class GoogleOAuthManager {
  private config: GoogleOAuthConfig;
  private mockMode: boolean;
  private mockTokenEndpoint: string;
  private mockTokenInfoEndpoint: string;

  constructor(
    config?: Partial<GoogleOAuthConfig>,
    options?: { mockTokenEndpoint?: string; mockTokenInfoEndpoint?: string }
  ) {
    this.config = {
      clientId: config?.clientId || process.env.GOOGLE_CLIENT_ID || '',
      clientSecret: config?.clientSecret || process.env.GOOGLE_CLIENT_SECRET || '',
      redirectUri: config?.redirectUri || process.env.GOOGLE_REDIRECT_URI || '',
      scopes: config?.scopes || DEFAULT_SCOPES,
    };

    // Mock mode for testing with Mockoon
    this.mockMode = !this.config.clientId || process.env.MOCK_MODE === 'true';
    this.mockTokenEndpoint =
      options?.mockTokenEndpoint || process.env.MOCK_OAUTH_TOKEN_URL || 'http://localhost:3001/oauth2/v4/token';
    this.mockTokenInfoEndpoint =
      options?.mockTokenInfoEndpoint || process.env.MOCK_OAUTH_INFO_URL || 'http://localhost:3001/oauth2/v2/tokeninfo';
  }

  /**
   * Generate authorization URL for OAuth2 flow
   */
  generateAuthUrl(state?: string, accessType: 'offline' | 'online' = 'offline'): OAuthFlowResponse {
    const generatedState = state || generateState();
    const params = new URLSearchParams({
      client_id: this.config.clientId,
      redirect_uri: this.config.redirectUri,
      response_type: 'code',
      scope: this.config.scopes.join(' '),
      access_type: accessType,
      prompt: accessType === 'offline' ? 'consent' : 'select_account',
      state: generatedState,
    });

    // In mock mode, return mock URL
    const authUrl = this.mockMode
      ? `http://localhost:3001/o/oauth2/v2/auth?${params.toString()}`
      : `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;

    return {
      authUrl,
      state: generatedState,
      expiresAt: Date.now() + 600000, // 10 minutes
    };
  }

  /**
   * Exchange authorization code for tokens
   */
  async exchangeCodeForTokens(code: string): Promise<TokenResponse> {
    if (this.mockMode) {
      return this.mockExchangeCode(code);
    }

    try {
      const response = await fetch(this.mockTokenEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          client_id: this.config.clientId,
          client_secret: this.config.clientSecret,
          code,
          redirect_uri: this.config.redirectUri,
          grant_type: 'authorization_code',
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        return { success: false, error: `Token exchange failed: ${error}` };
      }

      const token: GoogleOAuthToken = await response.json();
      return {
        success: true,
        accessToken: token.access_token,
        expiresAt: Date.now() + token.expires_in * 1000,
      };
    } catch (error) {
      return { success: false, error: `Network error: ${(error as Error).message}` };
    }
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshAccessToken(refreshToken: string): Promise<TokenResponse> {
    if (this.mockMode) {
      return this.mockRefreshToken(refreshToken);
    }

    try {
      const response = await fetch(this.mockTokenEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          client_id: this.config.clientId,
          client_secret: this.config.clientSecret,
          refresh_token: refreshToken,
          grant_type: 'refresh_token',
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        return { success: false, error: `Token refresh failed: ${error}` };
      }

      const token: GoogleOAuthToken = await response.json();
      return {
        success: true,
        accessToken: token.access_token,
        expiresAt: Date.now() + token.expires_in * 1000,
      };
    } catch (error) {
      return { success: false, error: `Network error: ${(error as Error).message}` };
    }
  }

  /**
   * Validate token and get info
   */
  async validateToken(accessToken: string): Promise<{ valid: boolean; email?: string; expiresIn?: number }> {
    if (this.mockMode) {
      return { valid: true, expiresIn: 3600 };
    }

    try {
      const response = await fetch(`${this.mockTokenInfoEndpoint}?access_token=${accessToken}`);

      if (!response.ok) {
        return { valid: false };
      }

      const data = await response.json();
      return {
        valid: data.verified_email === true,
        email: data.email,
        expiresIn: data.expires_in,
      };
    } catch {
      return { valid: false };
    }
  }

  /**
   * Create stored credentials object
   */
  createStoredCredentials(
    userId: string,
    token: GoogleOAuthToken
  ): StoredGoogleCredentials {
    return {
      userId,
      accessToken: token.access_token,
      refreshToken: token.refresh_token || '',
      expiresAt: Date.now() + token.expires_in * 1000,
      scope: token.scope,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  }

  /**
   * Check if token is expired
   */
  isTokenExpired(credentials: StoredGoogleCredentials): boolean {
    return Date.now() >= credentials.expiresAt - 60000; // 1 minute buffer
  }

  /**
   * Get valid access token (refresh if needed)
   */
  async getValidAccessToken(credentials: StoredGoogleCredentials): Promise<TokenResponse> {
    if (this.isTokenExpired(credentials)) {
      return this.refreshAccessToken(credentials.refreshToken);
    }
    return { success: true, accessToken: credentials.accessToken };
  }

  // ============ Mock Methods for Testing ============

  /**
   * Mock token exchange for testing
   */
  private async mockExchangeCode(_code: string): Promise<TokenResponse> {
    // Simulate successful token exchange
    return {
      success: true,
      accessToken: 'mock_access_token_' + generateState().slice(0, 8),
      expiresAt: Date.now() + 3600000,
    };
  }

  /**
   * Mock token refresh for testing
   */
  private async mockRefreshToken(_refreshToken: string): Promise<TokenResponse> {
    // Simulate successful token refresh
    return {
      success: true,
      accessToken: 'mock_refreshed_token_' + generateState().slice(0, 8),
      expiresAt: Date.now() + 3600000,
    };
  }
}

/**
 * Singleton instance for easy use (exported for testing)
 */
let oauthManager: GoogleOAuthManager | null = null;

export function resetOAuthManager(): void {
  oauthManager = null;
}

export function getOAuthManager(
  config?: Partial<GoogleOAuthConfig>,
  options?: { mockTokenEndpoint?: string; mockTokenInfoEndpoint?: string }
): GoogleOAuthManager {
  if (!oauthManager) {
    oauthManager = new GoogleOAuthManager(config, options);
  }
  return oauthManager;
}
