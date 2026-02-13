/**
 * Google Integration Module
 *
 * Google OAuth2 and Sheets API integration for Invoicify.
 *
 * Usage:
 *   import { GoogleOAuthManager, GoogleSheetsClient, detectSchema } from './lib/google';
 *
 *   // Initialize OAuth
 *   const oauth = getOAuthManager();
 *   const { authUrl, state } = oauth.generateAuthUrl();
 *
 *   // Exchange code for tokens
 *   const { accessToken } = await oauth.exchangeCodeForTokens(code);
 *
 *   // Create Sheets client
 *   const sheets = new GoogleSheetsClient(accessToken);
 *   const { data } = await sheets.getSpreadsheet(spreadsheetId);
 *
 *   // Map invoice to row
 *   const row = invoiceToRow(invoice, schema);
 */

export * from './types.js';
export * from './oauth.js';
export * from './sheets.js';
export * from './schema-mapper.js';
