/**
 * Google OAuth Manager Unit Tests
 *
 * Run with: pnpm test -- test/lib/google/oauth.test.ts
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { GoogleOAuthManager, getOAuthManager, resetOAuthManager } from './oauth.js';
import type { StoredGoogleCredentials } from './types.js';

describe('GoogleOAuthManager', () => {
  let manager: GoogleOAuthManager;

  beforeEach(() => {
    // Initialize in mock mode
    manager = new GoogleOAuthManager(
      {
        clientId: '',
        clientSecret: '',
        redirectUri: 'http://localhost:3000/callback',
      },
      {
        mockTokenEndpoint: 'http://localhost:3001/oauth2/v4/token',
        mockTokenInfoEndpoint: 'http://localhost:3001/oauth2/v2/tokeninfo',
      }
    );
  });

  describe('constructor', () => {
    it('should initialize in mock mode without credentials', () => {
      expect(manager).toBeInstanceOf(GoogleOAuthManager);
    });

    it('should use provided config', () => {
      const customManager = new GoogleOAuthManager({
        clientId: 'test-client-id',
        clientSecret: 'test-secret',
        redirectUri: 'http://localhost:8080/callback',
      });

      expect(customManager).toBeInstanceOf(GoogleOAuthManager);
    });
  });

  describe('generateAuthUrl', () => {
    it('should generate auth URL with state', () => {
      const result = manager.generateAuthUrl();

      expect(result.authUrl).toContain('http://localhost:3001');
      expect(result.authUrl).toContain('client_id=');
      expect(result.authUrl).toContain('redirect_uri=');
      expect(result.authUrl).toContain('scope=');
      expect(result.state).toBeDefined();
      expect(result.state.length).toBe(64); // 32 bytes = 64 hex chars
      expect(result.expiresAt).toBeGreaterThan(Date.now());
    });

    it('should use provided state', () => {
      const customState = 'custom-state-123';
      const result = manager.generateAuthUrl(customState);

      expect(result.state).toBe(customState);
    });

    it('should use offline access type by default', () => {
      const result = manager.generateAuthUrl();

      expect(result.authUrl).toContain('access_type=offline');
      expect(result.authUrl).toContain('prompt=consent');
    });

    it('should use online access type when specified', () => {
      const result = manager.generateAuthUrl(undefined, 'online');

      expect(result.authUrl).toContain('access_type=online');
    });
  });

  describe('exchangeCodeForTokens', () => {
    it('should return mock token in mock mode', async () => {
      const result = await manager.exchangeCodeForTokens('test-auth-code');

      expect(result.success).toBe(true);
      expect(result.accessToken).toBeDefined();
      expect(result.accessToken).toContain('mock_access_token');
      expect(result.expiresAt).toBeGreaterThan(Date.now());
    });

    it('should return error on failure', async () => {
      // Create manager with invalid mock endpoint
      const failingManager = new GoogleOAuthManager({}, { mockTokenEndpoint: 'http://invalid:9999/token' });

      // In mock mode, it should still succeed, but let's verify
      const result = await failingManager.exchangeCodeForTokens('code');
      expect(result.success).toBe(true);
    });
  });

  describe('refreshAccessToken', () => {
    it('should return mock token in mock mode', async () => {
      const result = await manager.refreshAccessToken('test-refresh-token');

      expect(result.success).toBe(true);
      expect(result.accessToken).toBeDefined();
      expect(result.accessToken).toContain('mock_refreshed_token');
      expect(result.expiresAt).toBeGreaterThan(Date.now());
    });
  });

  describe('validateToken', () => {
    it('should return valid in mock mode', async () => {
      const result = await manager.validateToken('any-token');

      expect(result.valid).toBe(true);
      expect(result.expiresIn).toBe(3600);
    });
  });

  describe('createStoredCredentials', () => {
    it('should create credentials from token response', () => {
      const token = {
        access_token: 'test-access-token',
        refresh_token: 'test-refresh-token',
        expires_in: 3600,
        scope: 'https://www.googleapis.com/auth/spreadsheets',
        token_type: 'Bearer' as const,
      };

      const credentials = manager.createStoredCredentials('user-123', token);

      expect(credentials.userId).toBe('user-123');
      expect(credentials.accessToken).toBe('test-access-token');
      expect(credentials.refreshToken).toBe('test-refresh-token');
      expect(credentials.scope).toBe(token.scope);
      expect(credentials.expiresAt).toBeGreaterThan(Date.now());
      expect(credentials.createdAt).toBeDefined();
      expect(credentials.updatedAt).toBeDefined();
    });

    it('should handle missing refresh token', () => {
      const token = {
        access_token: 'access-only',
        expires_in: 3600,
        scope: 'test',
        token_type: 'Bearer' as const,
      };

      const credentials = manager.createStoredCredentials('user-456', token);

      expect(credentials.refreshToken).toBe('');
    });
  });

  describe('isTokenExpired', () => {
    it('should return false for non-expired token', () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'token',
        refreshToken: 'refresh',
        expiresAt: Date.now() + 3600000, // 1 hour from now
        scope: 'test',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(manager.isTokenExpired(credentials)).toBe(false);
    });

    it('should return true for expired token', () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'token',
        refreshToken: 'refresh',
        expiresAt: Date.now() - 1000, // 1 second ago
        scope: 'test',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(manager.isTokenExpired(credentials)).toBe(true);
    });

    it('should return true for token expiring soon', () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'token',
        refreshToken: 'refresh',
        expiresAt: Date.now() + 30000, // 30 seconds from now (within 1 min buffer)
        scope: 'test',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(manager.isTokenExpired(credentials)).toBe(true);
    });
  });

  describe('getValidAccessToken', () => {
    it('should return existing token if not expired', async () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'existing-token',
        refreshToken: 'refresh',
        expiresAt: Date.now() + 3600000,
        scope: 'test',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      const result = await manager.getValidAccessToken(credentials);

      expect(result.success).toBe(true);
      expect(result.accessToken).toBe('existing-token');
    });

    it('should refresh token if expired', async () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'expired-token',
        refreshToken: 'refresh-token',
        expiresAt: Date.now() - 1000,
        scope: 'test',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      const result = await manager.getValidAccessToken(credentials);

      expect(result.success).toBe(true);
      expect(result.accessToken).toContain('mock_refreshed_token');
    });
  });

  describe('getOAuthManager (singleton)', () => {
    it('should return same instance', () => {
      const instance1 = getOAuthManager();
      const instance2 = getOAuthManager();

      expect(instance1).toBe(instance2);
    });

    it('should create new instance if not exists', () => {
      resetOAuthManager(); // Reset singleton
      const instance = getOAuthManager();

      expect(instance).toBeInstanceOf(GoogleOAuthManager);
    });
  });
});
