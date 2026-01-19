/**
 * Invoicify E2E Tests with Playwright
 *
 * Run with: pnpm exec playwright test e2e/
 * Or: npx playwright test e2e/ --reporter=line
 *
 * Prerequisites:
 * 1. Frontend: pnpm dev (runs on port 3000)
 * 2. Backend: wrangler dev (runs on port 8787)
 * 3. Services: docker compose up (postgres, redis, neo4j)
 */

import { test, expect } from '@playwright/test';

test.describe('Invoicify Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Clear local storage for clean test state
    await page.goto('http://localhost:3000');
  });

  test('should load dashboard page', async ({ page }) => {
    // Check main navigation heading (unique in nav)
    await expect(page.locator('nav h1')).toContainText('Invoicify AI');

    // Check navigation exists (use nav link specifically to avoid heading conflict)
    await expect(page.locator('nav a:has-text("Dashboard")')).toBeVisible();
    await expect(page.locator('nav a:has-text("Invoices")')).toBeVisible();
    await expect(page.locator('nav a:has-text("HITL Review")')).toBeVisible();
    await expect(page.locator('nav a:has-text("Audit Trail")')).toBeVisible();
  });

  test('should display KPI cards', async ({ page }) => {
    // Check KPI cards are present
    await expect(page.locator('text=Total Invoices')).toBeVisible();
    await expect(page.locator('text=Pending Review')).toBeVisible();
    await expect(page.locator('text=Avg Amount')).toBeVisible();
    await expect(page.locator('text=Critical Risk')).toBeVisible();
  });

  test('should navigate to invoices page', async ({ page }) => {
    await page.click('text=Invoices');
    await expect(page).toHaveURL(/.*invoices/);
  });

  test('should navigate to HITL review page', async ({ page }) => {
    await page.click('text=HITL Review');
    await expect(page).toHaveURL(/.*hitl/);
  });

  test('should navigate to audit trail page', async ({ page }) => {
    await page.click('text=Audit Trail');
    await expect(page).toHaveURL(/.*audit/);
  });
});

test.describe('Invoicify Invoices Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/invoices');
  });

  test('should display invoices page', async ({ page }) => {
    // Check that we're on invoices page
    await expect(page).toHaveURL(/.*invoices/);
    // Check navigation still works
    await expect(page.locator('text=Dashboard')).toBeVisible();
  });
});

test.describe('Invoicify HITL Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/hitl');
  });

  test('should display HITL review page', async ({ page }) => {
    await expect(page).toHaveURL(/.*hitl/);
    // Check navigation still works
    await expect(page.locator('text=Dashboard')).toBeVisible();
  });
});

test.describe('Invoicify Audit Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/audit');
  });

  test('should display audit trail page', async ({ page }) => {
    await expect(page).toHaveURL(/.*audit/);
    // Check navigation still works
    await expect(page.locator('text=Dashboard')).toBeVisible();
  });
});

test.describe('Navigation', () => {
  test('should allow navigation through all main sections', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Dashboard -> Invoices
    await page.click('text=Invoices');
    await expect(page).toHaveURL(/.*invoices/);

    // Invoices -> HITL
    await page.click('text=HITL Review');
    await expect(page).toHaveURL(/.*hitl/);

    // HITL -> Audit
    await page.click('text=Audit Trail');
    await expect(page).toHaveURL(/.*audit/);

    // Audit -> Dashboard
    await page.click('text=Dashboard');
    await expect(page).toHaveURL(/.*\/$/);
  });
});
